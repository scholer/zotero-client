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

# pylint: disable=C0103

"""
Testing module for pyzotero.awsfile

"""

TEST_BYTES = bytes(i for i in range(2**8))
HEAD = b"HEAD"
TAIL = b"TAIL"

import sys
import os
import tempfile

# Insert package directory in sys.path:
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from pyzotero import awsfile

def test_awsfile_output():
    """
    Make sure that AWSfile produces the correct output.
    """
    _, filepath = tempfile.mkstemp()
    #print("fd:", fd, type(fd))
    with open(filepath, 'wb') as fd:
        fd.write(TEST_BYTES)
    aws = awsfile.AWSfile(HEAD, filepath, TAIL)
    filebytes = open(filepath, 'rb').read()
    awsbytearray = aws.read()
    assert HEAD+filebytes+TAIL == bytes(awsbytearray)


def test_awsfile_string():
    """
    Make sure that AWSfile produces the correct output.
    """
    _, filepath = tempfile.mkstemp()
    head = "head"
    tail = "tailæøå"
    with open(filepath, 'wb') as fd:
        fd.write(TEST_BYTES)
    aws = awsfile.AWSfile(head, filepath, tail)
    filebytes = open(filepath, 'rb').read()
    awsbytearray = aws.read()
    assert head.encode('utf-8')+filebytes+tail.encode('utf-8') == bytes(awsbytearray)



if __name__ == '__main__':
    test_awsfile_output()
