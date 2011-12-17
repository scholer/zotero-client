#!/usr/bin/env python
# -*- coding: utf-8 -*-
import xml.etree.ElementTree as et

def etags(incoming):
      """ Return a list of etags parsed out of the XML response
      """
      # Parse Atom as straight XML in order to get the etags FFS
      atom_ns = '{http://www.w3.org/2005/Atom}'
      tree = et.fromstring(incoming)
      return [entry.attrib['{http://zotero.org/ns/api}etag'] for
          entry in tree.findall('.//{0}content'.format(atom_ns))]

x = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom" xmlns:zapi="http://zotero.org/ns/api">
          <title>Zotero / urschrei / Items</title>
          <id>http://zotero.org/users/436/items?limit=3&amp;content=json</id>
          <link rel="self" type="application/atom+xml" href="https://api.zotero.org/users/436/items?limit=1&amp;content=json"/>
          <link rel="first" type="application/atom+xml" href="https://api.zotero.org/users/436/items?limit=1&amp;content=json"/>
          <link rel="next" type="application/atom+xml" href="https://api.zotero.org/users/436/items?limit=1&amp;content=json&amp;start=3"/>
          <link rel="last" type="application/atom+xml" href="https://api.zotero.org/users/436/items?limit=1&amp;content=json&amp;start=1086"/>
          <link rel="alternate" type="text/html" href="http://zotero.org/users/436/items?limit=1"/>
          <zapi:totalResults>1087</zapi:totalResults>
          <zapi:apiVersion>1</zapi:apiVersion>
          <updated>2011-05-28T11:07:58Z</updated>
          <entry>
            <title>Copyright in custom code: Who owns commissioned software?</title>
            <author>
              <name>urschrei</name>
              <uri>http://zotero.org/urschrei</uri>
            </author>
            <id>http://zotero.org/urschrei/items/T4AH4RZA</id>
            <published>2011-02-14T00:27:03Z</published>
            <updated>2011-02-14T00:27:03Z</updated>
            <link rel="self" type="application/atom+xml" href="https://api.zotero.org/users/436/items/T4AH4RZA?content=json"/>
            <link rel="alternate" type="text/html" href="http://zotero.org/urschrei/items/T4AH4RZA"/>
            <zapi:key>T4AH4RZA</zapi:key>
            <zapi:itemType>journalArticle</zapi:itemType>
            <zapi:creatorSummary>McIntyre</zapi:creatorSummary>
            <zapi:numChildren>1</zapi:numChildren>
            <zapi:numTags>0</zapi:numTags>
            <content type="application/json" zapi:etag="7252daf2495feb8ec89c61f391bcba24">{"itemType":"journalArticle","title":"Copyright in custom code: Who owns commissioned software?","creators":[{"creatorType":"author","firstName":"T. J.","lastName":"McIntyre"}],"abstractNote":"","publicationTitle":"Journal of Intellectual Property Law \u0026 Practice","volume":"","issue":"","pages":"","date":"2007","series":"","seriesTitle":"","seriesText":"","journalAbbreviation":"","language":"","DOI":"","ISSN":"1747-1532","shortTitle":"Copyright in custom code","url":"","accessDate":"","archive":"","archiveLocation":"","libraryCatalog":"Google Scholar","callNumber":"","rights":"","extra":"","tags":[]}</content>
          </entry>
        </feed>"""
y = """<?xml version="1.0"?>
        <entry xmlns="http://www.w3.org/2005/Atom" xmlns:zapi="http://zotero.org/ns/api">
          <title>Hell, I don't Know</title>
          <author>
            <name>urschrei</name>
            <uri>http://zotero.org/urschrei</uri>
          </author>
          <id>http://zotero.org/urschrei/items/NVGIBE59</id>
          <published>2011-12-14T19:24:20Z</published>
          <updated>2011-12-17T19:19:37Z</updated>
          <link rel="self" type="application/atom+xml" href="https://api.zotero.org/users/436/items/NVGIBE59?content=json"/>
          <link rel="alternate" type="text/html" href="http://zotero.org/urschrei/items/NVGIBE59"/>
          <zapi:key>NVGIBE59</zapi:key>
          <zapi:itemType>journalArticle</zapi:itemType>
          <zapi:creatorSummary>Salo</zapi:creatorSummary>
          <zapi:year/>
          <zapi:numChildren>1</zapi:numChildren>
          <zapi:numTags>0</zapi:numTags>
          <content type="application/json" zapi:etag="1ed002db69174ae2ae0e3b90499df15e">{"itemType":"journalArticle","title":"Hell, I don't Know","creators":[{"creatorType":"author","firstName":"Dorotea","lastName":"Salo"}],"abstractNote":"","publicationTitle":"","volume":"","issue":"","pages":"","date":"","series":"","seriesTitle":"","seriesText":"","journalAbbreviation":"","language":"","DOI":"","ISSN":"","shortTitle":"","url":"","accessDate":"","archive":"","archiveLocation":"","libraryCatalog":"","callNumber":"","rights":"","extra":"","tags":[]}</content>
        </entry>"""

print etags(x)
print etags(y)