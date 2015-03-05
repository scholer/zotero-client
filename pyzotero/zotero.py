# -*- coding: utf-8 -*-
# pylint: disable=R0904,C0103,W0142
"""
zotero.py

Created by Stephan Hügel on 2011-02-28
Copyright Stephan Hügel, 2011-2015
Copyright Rasmus S. Sorensen, 2015

This file is part of Pyzotero.

Pyzotero is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Pyzotero is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Pyzotero. If not, see <http://www.gnu.org/licenses/>.

"""

from __future__ import unicode_literals, absolute_import

__author__ = u'Stephan Hügel'
__version__ = '1.1.4'
__api_version__ = '3'

# Python 3 compatibility faffing
try:
    from urllib import urlencode
    from urllib import quote
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlencode
    from urllib.parse import urlparse
    from urllib.parse import quote

import requests
import socket
import feedparser
import json
import copy
import uuid
import time
import os
import hashlib
import datetime
import re
import pytz
import mimetypes
import logging
logger = logging.getLogger(__name__)


try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict

from . import zotero_errors as ze
from .awsfile import AWSfile


# Avoid hanging the application if there's no server response
timeout = 30
socket.setdefaulttimeout(timeout)


def ib64_patched(self, attrsD, contentparams):
    """ Patch isBase64 to prevent Base64 encoding of JSON content
    """
    if attrsD.get('mode', '') == 'base64':
        return 0
    if self.contentparams['type'].startswith('text/'):
        return 0
    if self.contentparams['type'].endswith('+xml'):
        return 0
    if self.contentparams['type'].endswith('/xml'):
        return 0
    if self.contentparams['type'].endswith('/json'):
        return 0
    return 0
# Override feedparser's buggy isBase64 method until they fix it
feedparser._FeedParserMixin._isBase64 = ib64_patched


def token():
    """ Return a unique 32-char write-token
    """
    return str(uuid.uuid4().hex)



def cleanwrap(func):
    """ Wrapper for Zotero._cleanup
    TODO: This wrapper seems unneccesary. Re-write Zotero._cleanup instead.
    """
    def enc(self, *args):
        """ Send each item to _cleanup() """
        return (func(self, item) for item in args)
    return enc


def retrieve(func):
    """
    Decorator for Zotero read API methods; calls _retrieve_data() and passes
    the result to the correct processor, based on a lookup.
    """
    def wrapped_f(self, *args, **kwargs):
        """
        Returns result of _retrieve_data()

        func's return value is part of a URI, and it's this
        which is intercepted and passed to _retrieve_data:
        '/users/123/items?key=abc123'
        """
        if kwargs:
            self.add_parameters(**kwargs)
        retrieved = self._retrieve_data(func(self, *args))
        # we now always have links in the header response
        self.links = self._extract_links()
        # determine content and format, based on url params
        content = self.content.search(
            self.response.url) and \
            self.content.search(
                self.response.url).group(0) or 'bib'
       # JSON by default
        formats = {
            'application/atom+xml': 'atom',
            'application/json': 'json',
            'text/plain': 'plain',
            }
        fmt = formats.get(self.response.headers['Content-Type'], 'json')
        # clear all query parameters
        self.url_params = None
        # Or process atom if it's atom-formatted
        if fmt == 'atom':
            parsed = feedparser.parse(retrieved)
            # select the correct processor
            processor = self.processors.get(content)
            # process the content correctly with a custom rule
            return processor(parsed)
        if self.tag_data:
            self.tag_data = False
            return self._tags_data(retrieved)
        # No need to do anything
        return retrieved
    return wrapped_f


class Zotero(object):
    """
    Zotero API methods
    A full list of methods can be found here:
    http://www.zotero.org/support/dev/server_api
    """
    def __init__(self, library_id=None, library_type=None, api_key=None,
                 preserve_json_order=False):
        """ Store Zotero credentials
        """
        self.endpoint = 'https://api.zotero.org'
        if library_id and library_type:
            self.library_id = library_id
            # library_type determines whether query begins w. /users or /groups
            self.library_type = library_type + 's'
        else:
            raise ze.MissingCredentials(
                'Please provide both the library ID and the library type')
        # api_key is not required for public user or group libraries
        # However, it should be defined, otherwise it'll raise AttributeErrors...
        self.api_key = api_key or ''
        self.preserve_json_order = preserve_json_order
        self.url_params = None
        self.tag_data = False
        self.response = None # It is a RESPONSE, not a Request object!
        # these aren't valid item fields, so never send them to the server
        self.temp_keys = set(['key', 'etag', 'group_id', 'updated'])
        # determine which processor to use for the parsed content
        self.fmt = re.compile(r'(?<=format=)\w+')
        self.content = re.compile(r'(?<=content=)\w+')
        self.processors = {
            'bib': self._bib_processor,
            'citation': self._citation_processor,
            'bibtex': self._bib_processor,
            'bookmarks': self._bib_processor,
            'coins': self._bib_processor,
            'csljson': self._csljson_processor,
            'mods': self._bib_processor,
            'refer': self._bib_processor,
            'rdf_bibliontology': self._bib_processor,
            'rdf_dc': self._bib_processor,
            'rdf_zotero': self._bib_processor,
            'ris': self._bib_processor,
            'tei': self._bib_processor,
            'wikipedia': self._bib_processor,
            'json': self._json_processor,
        }
        self.links = None
        self.session = requests.Session()
        self.templates = {}
        self.file_content_types = [
            'application/msword',
            'application/pdf',
            'application/octet-stream',
            'application/x-tex',
            'application/x-texinfo',
            'image/jpeg',
            'image/png',
            'image/gif',
            'image/tiff',
            'application/postscript',
            'application/rtf']
        logger.debug("Zotero client initialized with library_type/library_id: %s/%s and API key length: %s",
                     library_type, library_id, len(api_key) if api_key else api_key)

    @property
    def default_headers(self):
        """
        It's always OK to include these headers
        """
        return {
            "User-Agent": "Pyzotero/%s" % __version__,
            "Authorization": "Bearer %s" % self.api_key, # TODO: What if api_key is None?
            "Zotero-API-Version": "%s" % __api_version__,
            }


    def request(self, method, url, headers=None, **kwargs):
        """ Make requests.request to url using method injecting default headers, etc. """
        zot_headers = self.default_headers.copy()
        if headers is not None:
            zot_headers.update(headers)
        logger.debug("Making %s request to %s using headers %s",
                     method, url, zot_headers.keys())
        response = self.session.request(method, url, headers=zot_headers, **kwargs)
        logger.debug("%s from url %s with %s bytes", response, url, len(response.content))
        return response

    def get(self, url, headers=None, **kwargs):
        """ Convenience method to request get method. """
        kwargs.setdefault('allow_redirects', True)
        return self.request('get', url, headers=headers, **kwargs)

    def post(self, url, data=None, json=None, headers=None, **kwargs): # pylint: disable=W0621
        """ Convenience method to request post method. """
        return self.request('post', url, headers=headers, data=data, json=json, **kwargs)

    def put(self, url, data=None, headers=None, **kwargs):
        """ Convenience method to request put method. """
        return self.request('put', url, headers=headers, data=data, **kwargs)

    def patch(self, url, data=None, headers=None, **kwargs):
        """ Convenience method to request patch method. """
        return self.request('patch', url, headers=headers, data=data, **kwargs)

    def delete(self, url, headers=None, **kwargs):
        """ Convenience method to request patch method. """
        return self.request('patch', url, headers=headers, **kwargs)


    def _cache(self, template, key):
        """
        Add a retrieved template to the cache for 304 checking
        accepts a dict and key name, adds the retrieval time, and adds both
        to self.templates as a new dict using the specified key
        """
        # cache template and retrieval time for subsequent calls
        thetime = datetime.datetime.utcnow().replace(
            tzinfo=pytz.timezone('GMT'))
        self.templates[key] = {
            'tmplt': template,
            'updated': thetime}
        return copy.deepcopy(template)

    def _cleanup(self, to_clean):
        """ Remove keys we added for internal use
        """
        if isinstance(to_clean, list):
            return [self._cleanup(elem) for elem in to_clean]
        else:
            # Assume dict (if not, an AttributeError is a suitable error)
            return {k: v for k, v in to_clean.items() if k not in self.temp_keys}

    def _retrieve_data(self, request=None):
        """
        Retrieve Zotero items via the API
        Combine endpoint and request to access the specific resource
        Returns a JSON document
        """
        full_url = '%s%s' % (self.endpoint, request)
        self.response = self.get(full_url)
        if not self.response.ok:
            error_handler(self.response)
        content_type = self.response.headers['Content-Type'].lower()
        if content_type == 'application/json':
            return self.response.json()
        elif content_type in self.file_content_types:
            return self.response.content
        else:
            return self.response.text

    def _extract_links(self):
        """
        Extract self, first, next, last links from a request response
        """
        extracted = dict()
        try:
            for key, value in self.response.links.items():
                parsed = urlparse(value['url'])
                fragment = "{path}?{query}".format(
                    path=parsed[2],
                    query=parsed[4])
                extracted[key] = fragment
            return extracted
        except KeyError:
            # No links present, because it's a single item
            return None

    def _updated(self, url, payload, template=None):
        """
        Generic call to see if a template request returns 304 (Not Modified).
        Arguments:
        - <url>: a string to combine with the API endpoint.
                 (Yes, this would be the relative uri path or resource)
        - <payload>: a dict of format values, in case they're required by 'url'.
        - <template>: a template name to check for.
        As per the API docs, a template less than 1 hour old is
        assumed to be fresh, and will immediately return False if found.
        """
        # If the template is more than an hour old, try a 304
        if abs(datetime.datetime.utcnow().replace(tzinfo=pytz.timezone('GMT'))
               - self.templates[template]['updated']).seconds > 3600:
            query = self.endpoint + url.format(
                u=self.library_id,
                t=self.library_type,
                **payload)
            headers = {
                'If-Modified-Since':
                    payload['updated'].strftime("%a, %d %b %Y %H:%M:%S %Z")}
            # perform the request, and check whether the response returns 304
            r = self.get(query, headers=headers)
            if not r.ok:
                error_handler(r)
            return r.status_code == 304
        # Still plenty of life left in't
        return False

    def add_parameters(self, **params):
        """
        Add URL parameters
        Also ensure that only valid format/content combinations are requested
        """
        self.url_params = None
        # we want JSON by default
        if not params.get('format'):
            params['format'] = 'json'
        # non-standard content must be retrieved as Atom
        if params.get('content'):
            params['format'] = 'atom'
        # TODO: rewrite format=atom, content=json request

        self.url_params = urlencode(params)

    def _build_query(self, query_string, no_params=False):
        """
        Set request parameters. Will always add the user ID if it hasn't
        been specifically set by an API method
        """
        try:
            query = quote(query_string.format(
                u=self.library_id,
                t=self.library_type))
        except KeyError as err:
            raise ze.ParamNotPassed(
                'There\'s a request parameter missing: %s' % err)
        # Add the URL parameters and the user key, if necessary
        if no_params == False:
            if not self.url_params:
                self.add_parameters()
            query = '%s?%s' % (query, self.url_params)
        return query

    # The following methods are Zotero Read API calls
    def num_items(self):
        """ Return the total number of top-level items in the library
        """
        query = '/{t}/{u}/items/top'
        return self._totals(query)

    def num_collectionitems(self, collection):
        """ Return the total number of items in the specified collection
        """
        query = '/{t}/{u}/collections/{c}/items'.format(
            u=self.library_id,
            t=self.library_type,
            c=collection.upper())
        return self._totals(query)

    def num_tagitems(self, tag):
        """ Return the total number of items for the specified tag
        """
        query = '/{t}/{u}/tags/{ta}/items'.format(
            u=self.library_id,
            t=self.library_type,
            ta=tag)
        return self._totals(query)

    def _totals(self, query):
        """ General method for returning total counts
        """
        self.add_parameters(limit=1)
        query = self._build_query(query)
        data = self._retrieve_data(query)
        self.url_params = None
        # extract the 'total items' figure
        return int(self.response.headers['Total-Results'])

    @retrieve
    def key_info(self, **kwargs):
        """
        Retrieve info about the permissions associated with the
        key associated to the given Zotero instance
        """
        query_string = '/keys/{k}'.format(
            k=self.api_key)
        return self._build_query(query_string)

    @retrieve
    def items(self, **kwargs):
        """ Get user items
        """
        query_string = '/{t}/{u}/items'
        return self._build_query(query_string)

    def last_modified_version(self, **kwargs):
        """ Get the last modified version
        """
        self.items(**kwargs)
        return int(self.response.headers.get('last-modified-version', 0))

    @retrieve
    def top(self, **kwargs):
        """ Get user top-level items
        """
        query_string = '/{t}/{u}/items/top'
        return self._build_query(query_string)

    @retrieve
    def trash(self, **kwargs):
        """ Get all items in the trash
        """
        query_string = '/{t}/{u}/items/trash'
        return self._build_query(query_string)

    @retrieve
    def item(self, item, **kwargs):
        """ Get a specific item.
        Arg <item> is the item ID.
        """
        query_string = '/{t}/{u}/items/{i}'.format(
            u=self.library_id,
            t=self.library_type,
            i=item.upper())
        return self._build_query(query_string)

    @retrieve
    def file(self, item, **kwargs):
        """ Get the file from an specific item.
        Arg <item> is the item ID.
        """
        query_string = '/{t}/{u}/items/{i}/file'.format(
            u=self.library_id,
            t=self.library_type,
            i=item.upper())
        return self._build_query(query_string, no_params=True)

    @retrieve
    def children(self, item, **kwargs):
        """ Get a specific item's child items.
        Arg <item> is the item ID.
        """
        query_string = '/{t}/{u}/items/{i}/children'.format(
            u=self.library_id,
            t=self.library_type,
            i=item.upper())
        return self._build_query(query_string)

    @retrieve
    def collection_items(self, collection, **kwargs):
        """ Get a specific collection's items.
        Arg <collection> is the collection ID.
        """
        query_string = '/{t}/{u}/collections/{c}/items'.format(
            u=self.library_id,
            t=self.library_type,
            c=collection.upper())
        return self._build_query(query_string)

    @retrieve
    def collection(self, collection, **kwargs):
        """ Get user collection.
        Arg <collection> is the collection ID.
        """
        query_string = '/{t}/{u}/collections/{c}'.format(
            u=self.library_id,
            t=self.library_type,
            c=collection.upper())
        return self._build_query(query_string)

    @retrieve
    def collections(self, **kwargs):
        """ Get user collections (all of them).
        """
        query_string = '/{t}/{u}/collections'
        return self._build_query(query_string)

    @retrieve
    def collections_sub(self, collection, **kwargs):
        """ Get subcollections for a specific collection.
        Arg <collection> is the collection ID.
        """
        query_string = '/{t}/{u}/collections/{c}/collections'.format(
            u=self.library_id,
            t=self.library_type,
            c=collection.upper())
        return self._build_query(query_string)

    @retrieve
    def groups(self, **kwargs):
        """ Get user groups (all of them).
        """
        query_string = '/users/{u}/groups'
        return self._build_query(query_string)

    @retrieve
    def tags(self, **kwargs):
        """ Get tags
        """
        query_string = '/{t}/{u}/tags'
        self.tag_data = True
        return self._build_query(query_string)

    @retrieve
    def item_tags(self, item, **kwargs):
        """ Get tags for a specific item.
        Arg <item> is the item ID.
        """
        query_string = '/{t}/{u}/items/{i}/tags'.format(
            u=self.library_id,
            t=self.library_type,
            i=item.upper())
        self.tag_data = True
        return self._build_query(query_string)

    def all_top(self, **kwargs):
        """ Retrieve all top-level items
        """
        return self.everything(self.top(**kwargs))

    @retrieve
    def follow(self):
        """ Return the result of the call to the URL in the 'Next' link
        """
        if self.links.get('next'):
            return self.links.get('next')
        else:
            return None

    def iterfollow(self):
        """ Generator for self.follow()
        """
        # use same criterion as self.follow()
        if self.links is None:
            return
        while self.links.get('next'):
            yield self.follow()

    def makeiter(self, func):
        """ Return a generator of func's results
        """
        _ = func
        # reset the link. This results in an extra API call, yes
        self.links['next'] = self.links['self']
        return self.iterfollow()

    def everything(self, query):
        """
        Retrieve all items in the library for a particular query
        This method will override the 'limit' parameter if it's been set
        """
        items = []
        items.extend(query)
        while self.links.get('next'):
            items.extend(self.follow())
        return items

    def get_subset(self, subset):
        """
        Retrieve a subset of items
        Accepts a single argument: a list of item IDs
        """
        if len(subset) > 50:
            raise ze.TooManyItems(
                "You may only retrieve 50 items per call")
        # remember any url parameters that have been set
        params = self.url_params
        retr = []
        for itm in subset:
            retr.extend(self.item(itm))
            self.url_params = params
        # clean up URL params when we're finished
        self.url_params = None
        return retr

    # The following methods process data returned by Read API calls
    def _json_processor(self, retrieved):
        """ Format and return data from API calls which return Items
        """
        json_kwargs = {}
        if self.preserve_json_order:
            json_kwargs['object_pairs_hook'] = OrderedDict
        # send entries to _tags_data if there's no JSON
        try:
            items = [json.loads(e['content'][0]['value'], **json_kwargs)
                     for e in retrieved.entries]
        except KeyError:
            return self._tags_data(retrieved)
        return items

    def _csljson_processor(self, retrieved):
        """ Return a list of dicts which are dumped CSL JSON
        """
        items = []
        json_kwargs = {}
        if self.preserve_json_order:
            json_kwargs['object_pairs_hook'] = OrderedDict
        for csl in retrieved.entries:
            items.append(json.loads(csl['content'][0]['value'], **json_kwargs))
        self.url_params = None
        return items

    def _bib_processor(self, retrieved):
        """ Return a list of strings formatted as HTML bibliography entries
        """
        items = []
        for bib in retrieved.entries:
            items.append(bib['content'][0]['value'])
        self.url_params = None
        return items

    def _citation_processor(self, retrieved):
        """ Return a list of strings formatted as HTML citation entries
        """
        items = []
        for cit in retrieved.entries:
            items.append(cit['content'][0]['value'])
        self.url_params = None
        return items

    def _tags_data(self, retrieved):
        """ Format and return data from API calls which return Tags
        """
        tags = [t['tag'] for t in retrieved]
        self.url_params = None
        return tags

    # The following methods are Write API calls
    def item_template(self, itemtype):
        """ Get a template for a new item
        """
        # if we have a template and it hasn't been updated since we stored it
        template_name = 'item_template_' + itemtype
        query_string = '/items/new?itemType={i}'.format(
            i=itemtype)
        if self.templates.get(template_name) and not \
                self._updated(query_string,
                              self.templates[template_name],
                              template_name):
            return copy.deepcopy(self.templates[template_name]['tmplt'])
        # otherwise perform a normal request and cache the response
        retrieved = self._retrieve_data(query_string)
        return self._cache(retrieved, template_name)

    def _attachment_template(self, attachment_type):
        """
        Return a new attachment template of the required type:
        imported_file
        imported_url
        linked_file
        linked_url
        """
        return self.item_template('attachment&linkMode=' + attachment_type)

    def _attachment(self, payload, parentid=None):
        """
        Create attachments
        accepts a list of one or more attachment template dicts
        and an optional parent Item ID. If this is specified,
        attachments are created under this ID
        TODO: Add logging messages.
        TODO: Split out each function so they can be used outside.
        """
        def verify(files):
            """
            ensure that all files to be attached exist
            open()'s better than exists(), cos it avoids a race condition
            (Uhm, no, not when you close it again. But it does make sure the files
            are readable and not e.g. locked.)
            """
            for templt in files:
                if os.path.isfile(templt[u'filename']):
                    try:
                        # if it is a file, try to open it, and catch the error
                        with open(templt[u'filename']) as _:
                            pass
                    except IOError:
                        raise ze.FileDoesNotExist(
                            "The file at %s couldn't be opened or found." %
                            templt[u'filename'])
                # no point in continuing if the file isn't a file
                else:
                    raise ze.FileDoesNotExist(
                        "The file at %s couldn't be opened or found." %
                        templt[u'filename'])
            logger.info("Payload/files %s verified.", files)

        def create_prelim(payload, parentid=None):
            """
            Step 0: Register intent to upload files
            """
            verify(payload)
            liblevel = '/{t}/{u}/items'
            # Create one or more new attachments
            headers = {
                'Zotero-Write-Token': token(),
                'Content-Type': 'application/json',
            }
            # If we have a Parent ID, add it as a parentItem
            if parentid:
                for child in payload:
                    child['parentItem'] = parentid
            logger.info("Creating new attachment item with data: %s", payload)
            # This is a Response object, not a Request. So use r, res or resp as variable name.
            r = self.post(url=self.endpoint
                          + liblevel.format(t=self.library_type,
                                            u=self.library_id,),
                          json=payload,
                          headers=headers)
            if not r.ok:
                error_handler(r)
            data = r.json()
            logger.info("%s from new attachment item request with data: %s", r, data)
            return data

        def get_auth(attachment, reg_key):
            """
            Step 1: get upload authorisation for a file
            """
            mtypes = mimetypes.guess_type(attachment)
            digest = hashlib.md5()
            with open(attachment, 'rb') as att:
                for chunk in iter(lambda: att.read(8192), b''):
                    digest.update(chunk)
            auth_headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'If-None-Match': '*',
            }
            data = {
                'md5': digest.hexdigest(),
                'filename': os.path.basename(attachment),
                'filesize': os.path.getsize(attachment),
                'mtime': str(int(os.path.getmtime(attachment) * 1000)),
                'contentType': mtypes[0] or 'application/octet-stream',
                'charset': mtypes[1]
            }
            logger.info("Requesting file upload authorization for item %s with data %s.",
                        reg_key, data)
            auth_res = self.post(
                url=self.endpoint
                + '/users/{u}/items/{i}/file'.format( # TODO: Why is this /users/ and not /{t}/ ?
                    u=self.library_id,
                    i=reg_key),
                data=data,
                headers=auth_headers)
            # Should return status code 200 if authorized (and 403, 409, 412, 413, 428, 429 if not).
            if not auth_res.ok:
                error_handler(auth_res)
            logger.info("%s from file upload authorization request for item %s returned:\n%s",
                        auth_res, reg_key, auth_res.text)
            return auth_res.json()

        def uploadfile(authdata, reg_key):
            """
            Step 2: auth successful, and file not on server
            zotero.org/support/dev/server_api/file_upload#a_full_upload

            reg_key isn't used, but we need to pass it through to Step 3
            """
            upload_file = AWSfile(authdata['prefix'], attach, authdata['suffix'])
            # requests "files" argument is a dict/list with values
            # (filename, file-pointer, file-type, file-headers)
            upload_dict = {'file': (os.path.basename(attach), upload_file)}
            logger.info("Uploading file %s to %s, upload_dict has keys: %s",
                        attach, authdata['url'], upload_dict.keys())
            # NOTE: The fileserver is NOT api.zotero.org, but zoterofilestorage.s3.amazonaws.com
            # (This is also why attachment uploading is such a multi-step process...)
            # DO NOT ADD the DEFAULT zotero api HEADERS to this request.
            upload = requests.post(
                url=authdata['url'],
                files=upload_dict,
                headers={
                    "Content-Type": authdata['contentType'],
                    'User-Agent': 'Pyzotero/%s' % __version__})
            # status code should be 201 [Created]
            if not upload.ok:
                error_handler(upload)
            logger.info("%s from file upload request to %s of file %s: %s",
                        upload, authdata['url'], attach, upload.content)
            return register_upload(authdata, reg_key)

        def register_upload(authdata, reg_key):
            """
            Step 3: upload successful, so register it
            """
            reg_headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'If-None-Match': '*',
                'User-Agent': 'Pyzotero/%s' % __version__
            }
            reg_data = {
                'upload': authdata.get('uploadKey')
            }
            logger.info("Registering upload of item %s with authdata url %s and uploadkey %s",
                        reg_key, authdata['url'], authdata['uploadKey'])
            upload_reg = self.post(
                url=self.endpoint
                + '/users/{u}/items/{i}/file'.format(
                    u=self.library_id,
                    i=reg_key),
                data=reg_data,
                headers=reg_headers)
            # Response status code should be 204 [No content]
            if not upload_reg.ok:
                error_handler(upload_reg)
            logger.info("%s from upload registration request of attachment item %s: %s",
                        upload_reg, reg_key, upload_reg.content)

        # TODO: The flow needs to be a bit clearer
        # Current flow:
        # create_prelim:
        #  -- Check/verify that the files are readable.
        #  -- Create preliminary "attachment" items.
        # For each successfully registered item:
        #   get_auth(filename, key)
        #    -- post md5, filename, mtime, etc to '/users/{u}/items/{i}/file' and return parsed json.
        #   uploadfile(authdata, reg_key)
        #    -- Uploads file content with post to url in authdata.
        #    -- Calls register_upload(authdata, reg_key)
        # TODO: create_prelim sometimes fail, seemingly randomly.
        # That is, I can call zot.attachment_simple([file], parentid) and have it fail with json response:
        # {'failed': {'0': {'message': 'An error occurred', 'code': 500}}, 'unchanged': {}, 'success': {}}
        # Then I can run attachment_simple again afterwards, and it will succeed.
        # Maybe it is a timing/caching issue, i.e. the newly created parent has not been fully registered?
        created = create_prelim(payload, parentid)
        logger.info("Preliminary attachment item created: %s", created)
        registered_idx = [int(k) for k in created['success'].keys()]
        registered_keys = list(created['success'].values())
        logger.info("Succesfully registered indices and keys: %s and %s",
                    registered_idx, registered_keys)
        if registered_idx:
            # only upload and register authorised files
            # Uh, potential sporadic bug: .values() is not guaranteed to return the list in correct order.
            # I.e. registered_keys[r_idx] may not correspond to the correct key.
            # Also, python3 bug: dict_values object does not support indexing!
            for r_idx, r_content in enumerate(registered_idx):
                attach = payload[r_content]['filename']
                authdata = get_auth(attach, registered_keys[r_idx])
                # no need to keep going if the file exists
                if authdata == {"exists": 1}:
                    logger.info("File '%s' already exists on server.", attach)
                else:
                    logger.info("Received upload auth for file '%s', uploading and registering file for item %s.",
                                attach, registered_keys[r_idx])
                    logger.info("Authdata has keys: %s", authdata.keys())
                    uploadfile(authdata, registered_keys[r_idx])
        else:
            # TODO: Complain about failed registrations.
            logger.warning("No successfull preliminary attachment items created: %s", created)
        return created

    def add_tags(self, item, *tags):
        """
        Add one or more tags to a retrieved item,
        then update it on the server
        Accepts a dict, and one or more tags to add to it
        Returns the updated item from the server
        """
        # Make sure there's a tags field, or add one
        try:
            assert item['data']['tags']
        except AssertionError:
            item['data']['tags'] = list()
        for tag in tags:
            item['data']['tags'].append({u'tag': u'%s' % tag})
        # make sure everything's OK
        assert self.check_items([item])
        return self.update_item(item)

    def check_items(self, items):
        """
        Check that items to be created contain no invalid dict keys
        Accepts a single argument: a list of one or more dicts
        The retrieved fields are cached and re-used until a 304 call fails
        """
        # check for a valid cached version
        if self.templates.get('item_fields') and not \
                self._updated('/itemFields',
                              self.templates['item_fields'],
                              'item_fields'):
            template = set(
                t['field'] for t in self.templates['item_fields']['tmplt'])
        else:
            template = set(
                t['field'] for t in self.item_fields())
        # add fields we know to be OK
        template = template | set([
            'tags',
            'notes',
            'itemType',
            'creators',
            'mimeType',
            'linkMode',
            'note',
            'charset',
            'dateAdded',
            'version',
            'collections',
            'dateModified',
            'relations'])
        template = template | set(self.temp_keys)
        for pos, item in enumerate(items):
            to_check = set(i for i in item['data'].keys())
            difference = to_check.difference(template)
            if difference:
                raise ze.InvalidItemFields(
                    "Invalid keys present in item %s: %s" % \
                    (pos + 1, ' '.join(i for i in difference)))
        return [i['data'] for i in items]

    def item_types(self):
        """ Get all available item types
        """
        # Check for a valid cached version
        if self.templates.get('item_types') and not \
                self._updated('/itemTypes',
                              self.templates['item_types'],
                              'item_types'):
            return self.templates['item_types']['tmplt']
        query_string = '/itemTypes'
        # otherwise perform a normal request and cache the response
        retrieved = self._retrieve_data(query_string)
        return self._cache(retrieved, 'item_types') # Fixed: _retrieve_data already returns parsed json object.

    def creator_fields(self):
        """ Get localised creator fields
        """
        # Check for a valid cached version
        if self.templates.get('creator_fields') and not \
                self._updated('/creatorFields',
                              self.templates['creator_fields'],
                              'creator_fields'):
            return self.templates['creator_fields']['tmplt']
        query_string = '/creatorFields'
        # otherwise perform a normal request and cache the response
        retrieved = self._retrieve_data(query_string)
        return self._cache(retrieved, 'creator_fields')

    def item_type_fields(self, itemtype):
        """ Get all valid fields for an item
        """
        # check for a valid cached version
        template_name = 'item_type_fields_' + itemtype
        query_string = '/itemTypeFields?itemType={i}'.format(
            i=itemtype)
        if self.templates.get(template_name) and \
            not self._updated(query_string,
                              self.templates[template_name],
                              template_name):
            return self.templates[template_name]['tmplt']
        # otherwise perform a normal request and cache the response
        retrieved = self._retrieve_data(query_string)
        return self._cache(retrieved, template_name)

    def item_fields(self):
        """ Get all available item fields
        """
        # Check for a valid cached version
        if self.templates.get('item_fields') and not \
                self._updated('/itemFields',
                              self.templates['item_fields'],
                              'item_fields'):
            return self.templates['item_fields']['tmplt']
        query_string = '/itemFields'
        # otherwise perform a normal request and cache the response
        retrieved = self._retrieve_data(query_string)
        return self._cache(retrieved, 'item_fields')

    def item_creator_types(self, itemtype):
        """ Get all available creator types for an item
        """
        # check for a valid cached version
        template_name = 'item_creator_types_' + itemtype
        query_string = '/itemTypeCreatorTypes?itemType={i}'.format(
            i=itemtype)
        if self.templates.get(template_name) and not \
                self._updated(query_string,
                              self.templates[template_name],
                              template_name):
            return self.templates[template_name]['tmplt']
        # otherwise perform a normal request and cache the response
        retrieved = self._retrieve_data(query_string)
        return self._cache(retrieved, template_name)

    def create_items(self, payload):
        """
        Create new Zotero items
        Accepts one argument, a list containing one or more item dicts
        """
        if len(payload) > 50:
            raise ze.TooManyItems(
                "You may only create up to 50 items per call")
        # TODO: strip extra data if it's an existing item
        cleaned = self._cleanup(payload)
        headers = {
            'Zotero-Write-Token': token(),
            'Content-Type': 'application/json',
        }
        logger.debug("Creating items using data: %s", cleaned)
        r = self.post(
            url=self.endpoint
            + '/{t}/{u}/items'.format(
                t=self.library_type,
                u=self.library_id),
            json=cleaned,
            headers=headers)
        logger.info("%s from create items request with content: %s", r, r.content)
        if not r.ok:
            error_handler(r)
        return r.json()

    def create_collection(self, payload):
        """
        Create a new Zotero collection
        Accepts one argument, a list of dicts containing the following keys:

        'name': the name of the collection
        'parentCollection': OPTIONAL, the parent collection to which you wish to add this
        """
        # no point in proceeding if there's no 'name' key
        for item in payload:
            if 'name' not in item:
                raise ze.ParamNotPassed(
                    "The dict you pass must include a 'name' key")
            # add a blank 'parentCollection' key if it hasn't been passed
            if not 'parentCollection' in item:
                item['parentCollection'] = ''
        headers = {
            'Zotero-Write-Token': token(),
        }
        r = self.post(
            url=self.endpoint
            + '/{t}/{u}/collections'.format(
                t=self.library_type,
                u=self.library_id),
            headers=headers,
            json=payload)
        if not r.ok:
            error_handler(r)
        return r.text

    def update_collection(self, payload):
        """
        Update a Zotero collection property such as 'name'
        Accepts one argument, a dict containing collection data retrieved
        using e.g. 'collections()'
        """
        modified = payload['version']
        key = payload['key']
        headers = {'If-Unmodified-Since-Version': modified}
        r = self.put(
            url=self.endpoint
            + '/{t}/{u}/collections/{c}'.format(
                t=self.library_type, u=self.library_id, c=key),
            headers=headers,
            payload=json.dumps(payload))
        if not r.ok:
            error_handler(r)
        return True

    def attachment_simple(self, files, parentid=None, titles=None):
        """
        Add attachments.
        Arguments:
        <files> is a list of file paths to add as attachments.
        If <parentid> is given, then the files are attached as child items
        to the given parent item.
        <titles> is a list of title/file names for each file.
        If <titles> is not given, then the file's basename is used as title.
        TODO: Support for other attachment linkModes, especially linked_file.
        Zotero linkModes: imported_file,imported_url,linked_file,linked_url
        """
        orig = self._attachment_template('imported_file')
        to_add = [orig.copy() for fls in files]
        for idx, tmplt in enumerate(to_add):
            tmplt['title'] = titles[idx] if titles else os.path.basename(files[idx])
            tmplt['filename'] = files[idx]
        logger.info("Uploading attachments: %s", to_add)
        return self._attachment(to_add, parentid)

    def update_item(self, payload):
        """
        Update an existing item
        Accepts one argument, a dict containing Item data
        """
        to_send = self.check_items([payload])[0]
        modified = payload['version']
        ident = payload['key']
        headers = {'If-Unmodified-Since-Version': modified}
        r = self.put(
            url=self.endpoint
            + '/{t}/{u}/items/{id}'.format(
                t=self.library_type,
                u=self.library_id,
                id=ident),
            headers=headers,
            json=to_send)
        if not r.ok:
            error_handler(r)
        return True

    def addto_collection(self, collection, payload):
        """
        Add one or more items to a collection
        Accepts two arguments:
        The collection ID, and an item dict
        """
        ident = payload['key']
        modified = payload['version']
        # add the collection data from the item
        modified_collections = payload['data']['collections'] + list(collection)
        headers = {'If-Unmodified-Since-Version': modified}
        r = self.patch(
            url=self.endpoint
            + '/{t}/{u}/items/{i}'.format(
                t=self.library_type,
                u=self.library_id,
                i=ident),
            json={'collections': modified_collections},
            headers=headers)
        if not r.ok:
            error_handler(r)
        return True

    def deletefrom_collection(self, collection, payload):
        """
        Delete an item from a collection
        Accepts two arguments:
        The collection ID, and and an item dict
        """
        ident = payload['key']
        modified = payload['version']
        # strip the collection data from the item
        modified_collections = [
            c for c in payload['data']['collections'] if c != collection]
        headers = {'If-Unmodified-Since-Version': modified}
        r = self.patch(
            url=self.endpoint
            + '/{t}/{u}/items/{i}'.format(
                t=self.library_type,
                u=self.library_id,
                i=ident),
            json={'collections': modified_collections},
            headers=headers)
        if not r.ok:
            error_handler(r)
        return True

    def delete_item(self, payload):
        """
        Delete Items from a Zotero library
        Accepts a single argument:
            a dict containing item data
            OR a list of dicts containing item data
        TODO: Make this accept a key or list of keys, or make alternate method for that.
        (I expected this to work like Zotero.item(key) method)
        """
        params = None
        if isinstance(payload, list):
            params = {'itemKey': ','.join([p['key'] for p in payload])}
            modified = payload[0]['version']
            # TODO: NOT ALL ITEMS HAS THE SAME VERSION.
            url = self.endpoint + \
            '/{t}/{u}/items'.format(
                t=self.library_type,
                u=self.library_id)
        else:
            ident = payload['key']
            modified = payload['version']
            url = self.endpoint + \
            '/{t}/{u}/items/{c}'.format(
                t=self.library_type,
                u=self.library_id,
                c=ident)
        headers = {'If-Unmodified-Since-Version': modified}
        r = self.delete(
            url=url,
            params=params,
            headers=headers
        )
        if not r.ok:
            error_handler(r)
        return True

    def delete_collection(self, payload):
        """
        Delete a Collection from a Zotero library
        Accepts a single argument:
            a dict containing item data
            OR a list of dicts containing item data
        """
        params = None
        if isinstance(payload, list):
            params = {'collectionKey': ','.join([p['key'] for p in payload])}
            modified = payload[0]['version']
            url = self.endpoint + \
            '/{t}/{u}/collections'.format(
                t=self.library_type,
                u=self.library_id)
        else:
            ident = payload['key']
            modified = payload['version']
            url = self.endpoint + \
            '/{t}/{u}/collections/{c}'.format(
                t=self.library_type,
                u=self.library_id,
                c=ident)
        headers = {'If-Unmodified-Since-Version': modified}
        r = self.delete(
            url=url,
            params=params,
            headers=headers)
        if not r.ok:
            error_handler(r)
        return True


class Backoff(object):
    """ a simple backoff timer for HTTP 429 responses """
    def __init__(self, delay=1):
        self.wait = delay

    @property
    def delay(self):
        """ return increasing delays """
        self.wait = self.wait * 2
        return self.wait

    def reset(self):
        """ reset delay """
        self.wait = 1


backoff = Backoff()


def error_handler(req):
    """
    Error handler for HTTP requests.
    Handles "back off" responses etc.
    """
    error_codes = {
        400: ze.UnsupportedParams,
        401: ze.UserNotAuthorised,
        403: ze.UserNotAuthorised,
        404: ze.ResourceNotFound,
        409: ze.Conflict,
        412: ze.PreConditionFailed,
        413: ze.RequestEntityTooLarge,
        428: ze.PreConditionRequired,
        429: ze.TooManyRequests,
    }

    def err_msg(req):
        """ Return a nicely-formatted error message
        """
        return "\nCode: %s\nURL: %s\nMethod: %s\nResponse: %s" % (
            req.status_code,
            # error.msg,
            req.url,
            req.request.method,
            req.text)

    if error_codes.get(req.status_code):
        # check to see whether its 429
        if req.status_code == 429:
            # call our back-off function
            delay = backoff.delay
            if delay > 32:
                # we've waited a total of 62 seconds (2 + 4 … + 32), so give up
                backoff.reset()
                raise ze.TooManyRetries("Continuing to receive HTTP 429 \
responses after 62 seconds. You are being rate-limited, try again later")
            time.sleep(delay)
            sess = requests.Session()
            new_req = sess.send(req.request)
            if not new_req.ok:
                error_handler(new_req)
        else:
            raise error_codes.get(req.status_code)(err_msg(req))
    else:
        raise ze.HTTPError(err_msg(req))


if __name__ == '__main__':
    # Simple example on how to activate logging system:
    # logging.basicConfig()
    # Enable logging with customized output:
    production = False
    loguserfmt = "%(asctime)s %(levelname)-5s %(name)20s:%(lineno)-4s%(funcName)20s() %(message)s"
    logtimefmt = "%Y%m%d-%H:%M:%S" if production else "%H:%M:%S"
    logging.basicConfig(level=logging.WARNING if production else logging.DEBUG,
                        format=loguserfmt,
                        datefmt=logtimefmt)
