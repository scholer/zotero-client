#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for the Pyzotero module

Copyright Stephan Hügel, 2011

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

import os
import unittest
import httpretty
from httpretty import HTTPretty
# Usually, either (a) tests are run from the project root,
# or (b) the project root is added to the python path.
# This means that
# (1) the project root does not contain any __init__.py
# (2) the module directory is loaded with:
from pyzotero import zotero as z
from dateutil import parser

# Python 3 compatibility faffing
try:
    from urllib import urlencode
    from urllib import quote
    from urlparse import urlparse
    from urlparse import parse_qs
except ImportError:
    from urllib.parse import urlencode
    from urllib.parse import urlparse
    from urllib.parse import parse_qs
    from urllib.parse import quote


class ZoteroTests(unittest.TestCase):
    """ Tests for pyzotero
    """
    cwd = os.path.dirname(os.path.realpath(__file__))

    def get_doc(self, doc_name, cwd=cwd):
        """ return the requested test document """
        with open(os.path.join(cwd, 'api_responses', '%s' % doc_name), 'r') as f:
            return f.read()

    def setUp(self):
        """ Set stuff up
        """
        self.item_doc = self.get_doc('item_doc.json')
        self.items_doc = self.get_doc('items_doc.json')
        self.collections_doc = self.get_doc('collections_doc.json')
        self.collection_doc = self.get_doc('collection_doc.json')
        self.citation_doc = self.get_doc('citation_doc.xml')
        # self.biblio_doc = self.get_doc('bib_doc.xml')
        self.attachments_doc = self.get_doc('attachments_doc.json')
        self.tags_doc = self.get_doc('tags_doc.json')
        self.groups_doc = self.get_doc('groups_doc.json')
        self.item_templt = self.get_doc('item_template.json')
        self.item_types = self.get_doc('item_types.json')
        self.keys_response = self.get_doc('keys_doc.txt')
        self.creation_doc = self.get_doc('creation_doc.json')
        self.item_file = self.get_doc('item_file.pdf')
        # Add the item file to the mock response by default
        HTTPretty.enable()
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/users/myuserID/items',
            content_type='application/json',
            body=self.items_doc)

    @httpretty.activate
    def testFailWithoutCredentials(self):
        """ Instance creation should fail, because we're leaving out a
            credential
        """
        with self.assertRaises(z.ze.MissingCredentials):
            _ = z.Zotero('myuserID')

    @httpretty.activate
    def testRequestBuilder(self):
        """ Should url-encode all added parameters
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        zot.add_parameters(limit=0, start=7)
        self.assertEqual(
            parse_qs('start=7&limit=0&format=json'),
            parse_qs(zot.url_params))

    # @httpretty.activate
    # def testBuildQuery(self):
    #     """ Check that spaces etc. are being correctly URL-encoded and added
    #         to the URL parameters
    #     """
    #     orig = 'https://api.zotero.org/users/myuserID/tags/hi%20there/items?start=10&format=json'
    #     zot = z.Zotero('myuserID', 'user', 'myuserkey')
    #     zot.add_parameters(start=10)
    #     query_string = '/users/{u}/tags/hi there/items'
    #     query = zot._build_query(query_string)
    #     self.assertEqual(
    #         sorted(parse_qs(orig).items()),
    #         sorted(parse_qs(query).items()))

    @httpretty.activate
    def testParseItemJSONDoc(self):
        """ Should successfully return a list of item dicts, key should match
            input doc's zapi:key value, and author should have been correctly
            parsed out of the XHTML payload
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/users/myuserID/items',
            content_type='application/json',
            body=self.item_doc)
        items_data = zot.items()
        self.assertEqual(u'X42A7DEE', items_data['data']['key'])
        self.assertEqual(u'Institute of Physics (Great Britain)', items_data['data']['creators'][0]['name'])
        self.assertEqual(u'book', items_data['data']['itemType'])
        test_dt = parser.parse("2011-01-13T03:37:29Z")
        incoming_dt = parser.parse(items_data['data']['dateModified'])
        self.assertEqual(test_dt, incoming_dt)

    @httpretty.activate
    def testGetItemFile(self):
        """
        Should successfully return a binary string with a PDF content
        """
        zot = z.Zotero('myuserid', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/users/myuserid/items/MYITEMID/file',
            content_type='application/pdf',
            body=self.item_file)
        items_data = zot.file('myitemid')
        self.assertEqual(b'One very strange PDF\n', items_data)

    @httpretty.activate
    def testParseAttachmentsJSONDoc(self):
        """ Ensure that attachments are being correctly parsed """
        zot = z.Zotero('myuserid', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/users/myuserid/items',
            content_type='application/json',
            body=self.attachments_doc)
        attachments_data = zot.items()
        self.assertEqual(u'1641 Depositions', attachments_data['data']['title'])

    @httpretty.activate
    def testParseKeysResponse(self):
        """ Check that parsing plain keys returned by format = keys works """
        zot = z.Zotero('myuserid', 'user', 'myuserkey')
        zot.url_params = 'format=keys'
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/users/myuserid/items?format=keys',
            content_type='text/plain',
            body=self.keys_response)
        response = zot.items()
        self.assertEqual(u'JIFWQ4AN', response[:8])

    @httpretty.activate
    def testParseChildItems(self):
        """ Try and parse child items """
        zot = z.Zotero('myuserid', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/users/myuserid/items/ABC123/children',
            content_type='application/json',
            body=self.items_doc)
        items_data = zot.children('ABC123')
        self.assertEqual(u'NM66T6EF', items_data[0]['key'])

    @httpretty.activate
    def testCitUTF8(self):
        """ ensure that unicode citations are correctly processed by Pyzotero
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        url = 'https://api.zotero.org/users/myuserID/items/GW8V2CK7'
        HTTPretty.register_uri(
            HTTPretty.GET,
            url,
            content_type='application/atom+xml',
            body=self.citation_doc)
        cit = zot.item('GW8V2CK7', content='citation', style='chicago-author-date')
        self.assertEqual(
            cit[0],
            u'<span>(Ans\\xe6lm and Tka\\u010dik 2014)</span>')
    # @httpretty.activate
    # def testParseItemAtomBibDoc(self):
    #     """ Should match a DIV with class = csl-entry
    #     """
    #     zot = z.Zotero('myuserID', 'user', 'myuserkey')
    #     zot.url_params = 'content=bib'
    #     HTTPretty.register_uri(
    #         HTTPretty.GET,
    #         'https://api.zotero.org/users/myuserID/items?content=bib&format=atom',
    #         content_type='application/atom+xml',
    #         body=self.biblio_doc)
    #     items_data = zot.items()
    #     self.assertEqual(
    #         items_data[0],
    #         u'<div class="csl-entry">Robert A. Caro. \u201cThe Power Broker\u202f: Robert Moses and the Fall of New York,\u201d 1974.</div>'
    #         )

    @httpretty.activate
    def testParseCollectionJSONDoc(self):
        """ Should successfully return a single collection dict,
            'name' key value should match input doc's name value
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/users/myuserID/collections/KIMI8BSG',
            content_type='application/json',
            body=self.collection_doc)
        collections_data = zot.collection('KIMI8BSG')
        self.assertEqual(
            "LoC",
            collections_data['data']['name'])


    @httpretty.activate
    def testParseCollectionsJSONDoc(self):
        """ Should successfully return a list of collection dicts, key should
            match input doc's zapi:key value, and 'title' value should match
            input doc's title value
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/users/myuserID/collections',
            content_type='application/json',
            body=self.collections_doc)
        collections_data = zot.collections()
        self.assertEqual(
            "LoC",
            collections_data[0]['data']['name'])

    @httpretty.activate
    def testParseTagsJSON(self):
        """ Should successfully return a list of tags
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/users/myuserID/tags?limit=1',
            content_type='application/json',
            body=self.tags_doc)
        tags_data = zot.tags()
        self.assertEqual(u'Community / Economic Development', tags_data[0])

    @httpretty.activate
    def testParseGroupsJSONDoc(self):
        """ Should successfully return a list of group dicts, ID should match
            input doc's zapi:key value, and 'total_items' value should match
            input doc's zapi:numItems value
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/users/myuserID/groups',
            content_type='application/json',
            body=self.groups_doc)
        groups_data = zot.groups()
        self.assertEqual('smart_cities', groups_data[0]['data']['name'])

    def testParamsReset(self):
        """ Should successfully reset URL parameters after a query string
            is built
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        zot.add_parameters(start=5, limit=10)
        zot._build_query('/whatever')
        zot.add_parameters(start=2)
        self.assertEqual(
            parse_qs('start=2&format=json'),
            parse_qs(zot.url_params))

    @httpretty.activate
    def testParamsBlankAfterCall(self):
        """ self.url_params should be blank after an API call
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/users/myuserID/items',
            content_type='application/json',
            body=self.items_doc)
        _ = zot.items()
        self.assertEqual(None, zot.url_params)

    @httpretty.activate
    def testResponseForbidden(self):
        """ Ensure that an error is properly raised for 403
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/users/myuserID/items',
            content_type='application/json',
            body=self.items_doc,
            status=403)
        with self.assertRaises(z.ze.UserNotAuthorised):
            zot.items()

    @httpretty.activate
    def testResponseUnsupported(self):
        """ Ensure that an error is properly raised for 400
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/users/myuserID/items',
            content_type='application/json',
            body=self.items_doc,
            status=400)
        with self.assertRaises(z.ze.UnsupportedParams):
            zot.items()

    @httpretty.activate
    def testResponseNotFound(self):
        """ Ensure that an error is properly raised for 404
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/users/myuserID/items',
            body=self.items_doc,
            content_type='application/json',
            status=404)
        with self.assertRaises(z.ze.ResourceNotFound):
            zot.items()

    @httpretty.activate
    def testResponseMiscError(self):
        """ Ensure that an error is properly raised for unspecified errors
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/users/myuserID/items',
            content_type='application/json',
            body=self.items_doc,
            status=500)
        with self.assertRaises(z.ze.HTTPError):
            zot.items()

    @httpretty.activate
    def testGetItems(self):
        """ Ensure that we can retrieve a list of all items """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/itemTypes',
            content_type='application/json',
            body=self.item_types)
        t = zot.item_types()
        self.assertEqual(t[0]['itemType'], 'artwork')
        self.assertEqual(t[-1]['itemType'], 'webpage')

    @httpretty.activate
    def testGetTemplate(self):
        """ Ensure that item templates are retrieved and converted into dicts
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/items/new?itemType=book',
            content_type='application/json',
            body=self.item_templt)
        t = zot.item_template('book')
        self.assertEqual('book', t['itemType'])

    def testCreateCollectionError(self):
        """ Ensure that collection creation fails with the wrong dict
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        t = [{'foo': 'bar'}]
        with self.assertRaises(z.ze.ParamNotPassed):
            t = zot.create_collection(t)

    # @httpretty.activate
    # def testUpdateItem(self):
    #     """ Test that we can update an item
    #         This test is a kludge; it only tests that the mechanism for
    #         internal key removal is OK, and that we haven't made any silly
    #         list/dict comprehension or genexpr errors
    #     """
    #     import json
    #     # first, retrieve an item
    #     zot = z.Zotero('myuserID', 'user', 'myuserkey')
    #     HTTPretty.register_uri(
    #         HTTPretty.GET,
    #         'https://api.zotero.org/users/myuserID/items',
    #         body=self.items_doc)
    #     items_data = zot.items()
    #     items_data['title'] = 'flibble'
    #     json.dumps(*zot._cleanup(items_data))

    @httpretty.activate
    def testItemCreation(self):
        """ Tests creation of a new item using a template
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/items/new?itemType=book',
            body=self.item_templt,
            content_type='application/json')
        template = zot.item_template('book')
        httpretty.reset()
        HTTPretty.register_uri(
            HTTPretty.POST,
            'https://api.zotero.org/users/myuserID/items',
            body=self.creation_doc,
            content_type='application/json',
            status=200)
        # now let's test something
        resp = zot.create_items([template])
        self.assertEqual('ABC123', resp['success']['0'])

    @httpretty.activate
    def testAttachment(self):
        """
        Tests upload of new (non-existing) attachment.
        https://www.zotero.org/support/dev/web_api/v3/file_upload
        """
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        import tempfile
        fd, fn = tempfile.mkstemp()

        # Mock template request response
        att_template = """
{
    "itemType": "attachment",
    "linkMode": "imported_file",
    "title": "",
    "accessDate": "",
    "note": "",
    "tags": [],
    "contentType": "",
    "charset": "",
    "filename": "",
    "md5": null,
    "mtime": null
}"""
        HTTPretty.register_uri(
            HTTPretty.GET,
            'https://api.zotero.org/items/new?itemType=attachment&linkMode=imported_file',
            body=att_template,
            content_type='application/json',
            status=200)

        # Mock item creation (prelim) request response
        HTTPretty.register_uri(
            HTTPretty.POST,
            'https://api.zotero.org/users/myuserID/items',
            body=self.creation_doc, # 0: "ABC123"
            content_type='application/json',
            status=200)
        #
        # Mock upload auth request response:
        # (Auth request has qline formatted body, by the way...)
        auth_body = """{
  "url": "https://zoterofilestorage.s3.amazonaws.com/",
  "contentType": "multipart\/form-data; boundary=---------------------------f26db7247a034d450ede4b6e15902d82",
  "prefix": "-----------------------------f26db7247a034d450ede4b6e1590(...)",
  "suffix": "\\n-----------------------------f26db7247a034d450ede4b6e15902d82--",
  "uploadKey": "bdfff1b6699765839adac4d74f2635f3"
}"""
        HTTPretty.register_uri(
            HTTPretty.POST,
            # /users/<userID>/items/<itemKey>/file
            'https://api.zotero.org/users/myuserID/items/ABC123/file',
            body=auth_body,
            content_type='application/json',
            status=200)

        # Mock upload request response:
        aws_response = """<?xml version="1.0" encoding="UTF-8"?>\n<PostResponse><Location>https://zoterofilestorage.s3.amazonaws.com/0f6a49dc177dbc85dfac438883eee492</Location><Bucket>zoterofilestorage</Bucket><Key>0f6a49dc177dbc85dfac438883eee492</Key><ETag>"0f6a49dc177dbc85dfac438883eee492"</ETag></PostResponse>"""
        HTTPretty.register_uri(
            HTTPretty.POST,
            'https://zoterofilestorage.s3.amazonaws.com',
            body=aws_response,
            #content_type='application/json',
            status=201)

        # Register: Success returns 204 No Content.
        HTTPretty.register_uri(
            HTTPretty.POST,
            'https://api.zotero.org/users/96236/items/D4RXSHNV/file',
            body="",
            #content_type='application/json',
            status=204)
        # Test:
        resp = zot.attachment_simple([fn])
        self.assertEqual('ABC123', resp['success']['0'])


    def testTooManyItems(self):
        """ Should fail because we're passing too many items
        """
        itms = [i for i in range(51)]
        zot = z.Zotero('myuserID', 'user', 'myuserkey')
        with self.assertRaises(z.ze.TooManyItems):
            zot.create_items(itms)

    # @httprettified
    # def testRateLimit(self):
    #     """ Test 429 response handling (e.g. wait, wait a bit longer etc.)
    #     """
    #     zot = z.Zotero('myuserID', 'user', 'myuserkey')
    #     HTTPretty.register_uri(
    #         HTTPretty.GET,
    #         'https://api.zotero.org/users/myuserID/items',
    #         responses=[
    #             HTTPretty.Response(body=self.items_doc, status=429),
    #             HTTPretty.Response(body=self.items_doc, status=429),
    #             HTTPretty.Response(body=self.items_doc, status=200)])
    #     zot.items()
    #     with self.assertEqual(z.backoff.delay, 8):
    #         zot.items()

    def tearDown(self):
        """ Tear stuff down
        """
        HTTPretty.disable()


if __name__ == "__main__":
    unittest.main()
