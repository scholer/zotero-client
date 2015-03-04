#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (c) 2015 Rasmus Sorensen, rasmusscholer@gmail.com <scholer.github.io>

##    This program is free software: you can redistribute it and/or modify
##    it under the terms of the GNU General Public License as published by
##    the Free Software Foundation, either version 3 of the License, or
##    (at your option) any later version.
##
##    This program is distributed in the hope that it will be useful,
##    but WITHOUT ANY WARRANTY; without even the implied warranty of
##    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##    GNU General Public License for more details.
##
##    You should have received a copy of the GNU General Public License

# pylint: disable=C0103,W0142

# These are mocked during testing if MOCK_OPEN is specified:
from builtins import open   # Has to be explicitly imported so we can redefine it when testing.
from os.path import getsize


class AWSfile(object):
    """
    The purpose of this class is:
    1) Make it easy to create the file upload data.
    2) Ensure that file data is copied as little as possible.

    Currently, the file data is copied a total of five times.
    Although some of these matter little memory-wise, since the old data variable is
    carbage collected, the copy operations does affect performance.
    Based on timings from memory_consumption_tests.py:
        - Memory consumption cut from 2x filesize to 1x filesize (plus 1x in requests, which is out of our reach).
        - Request preparation time reduced by more than 50%
        - The improvement is noticable for files >10 MB

    (Note: These improvements are mostly for python 3 and less for python 2.7)

    Implementation alternatives:
    1) Use bytearray
    2) Use BytesIO and the memoryview returned by getbuffer()

    Refs:
    * http://eli.thegreenplace.net/2011/11/28/less-copies-in-python-with-the-buffer-protocol-and-memoryviews
    * docs.python.org/3/library/stdtypes.html
    * docs.python.org/3/c-api/buffer.html
    * http://bugs.python.org/issue5506, http://bugs.python.org/file18732/bytesiobuf2.patch
    """
    def __init__(self, head, filepath, tail, delayed=True):

        self._bytearray = None
        self._lens = None
        self._head = head
        self._filepath = filepath
        self._tail = tail
        if not delayed:
            self.make()

    def make(self):
        l = [len(self._head),
             getsize(self._filepath), # Careful: If this is wrong size, it fails silently.
             len(self._tail)]
        self._bytearray = bytearray(sum(l))
        mv = memoryview(self._bytearray)
        mv[:l[0]] = self._head
        with open(self._filepath, 'rb') as fp:
            fp.readinto(mv[sum(l[:1]):sum(l[:2])])
        mv[sum(l[:2]):sum(l[:3])] = self._tail

    def read(self):
        if self._bytearray is None:
            self.make()
        return self._bytearray
