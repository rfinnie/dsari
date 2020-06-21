# croniter_hash - Extend croniter with hash/random support
# Copyright (C) 2015-2020 Ryan Finnie
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

# Originally from:
# https://github.com/rfinnie/dsari

import binascii
import random
import re

import croniter


class croniter_hash(croniter.croniter):
    """Extend croniter with hash/random support

    All croniter.croniter functionality is supported; in addition,
    Jenkins-style "H" hashing is supported, or "R" for random.  Keyword
    argument "hash_id" (a croniter_hash-specific addition) is required
    for "H"/"R" definitions.
    """

    def __init__(self, expr_format, *args, **kwargs):
        if "hash_id" in kwargs:
            if kwargs["hash_id"]:
                expr_format = self._hash_expand(expr_format, kwargs["hash_id"])
            del kwargs["hash_id"]
        return super(croniter_hash, self).__init__(expr_format, *args, **kwargs)

    def _hash_do(self, id, position, range_end=None, range_begin=None, hash_type="H"):
        if not range_end:
            range_end = self.RANGES[position][1]
        if not range_begin:
            range_begin = self.RANGES[position][0]
        if hash_type == "R":
            crc = random.randint(0, 0xFFFFFFFF)
        else:
            if isinstance(id, bytes):
                id_bytes = id
            elif isinstance(id, str):
                id_bytes = id.encode("UTF-8")
            else:
                raise TypeError("id must be bytes or UTF-8 string")
            crc = binascii.crc32(id_bytes) & 0xFFFFFFFF
        return ((crc >> position) % (range_end - range_begin + 1)) + range_begin

    def _hash_expand(self, expr_format, id):
        if expr_format == "@midnight":
            expr_format = "H H(0-2) * * * H"
        elif expr_format == "@hourly":
            expr_format = "H * * * * H"
        elif expr_format == "@daily":
            expr_format = "H H * * * H"
        elif expr_format == "@weekly":
            expr_format = "H H * * H H"
        elif expr_format == "@monthly":
            expr_format = "H H H * * H"
        elif expr_format == "@yearly" or expr_format == "@annually":
            expr_format = "H H H H * H"

        expr_expanded = []
        for item in expr_format.split(" "):
            idx = len(expr_expanded)
            expr_expanded.append(self._hash_expand_item(item, id, idx))
        return " ".join(expr_expanded)

    def _hash_expand_item(self, item, id, idx):
        # Example: H -> 32
        if item in ("H", "R"):
            return str(self._hash_do(id, idx, hash_type=item))

        # Example: H(30-59)/10 -> 34-59/10 (i.e. 34,44,54)
        m = re.match(r"^(H|R)\((\d+)-(\d+)\)\/(\d+)$", item)
        if m:
            return "{}-{}/{}".format(
                self._hash_do(id, idx, int(m.group(4)), hash_type=m.group(1))
                + int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)),
            )

        # Example: H(0-29) -> 12
        m = re.match(r"^(H|R)\((\d+)-(\d+)\)$", item)
        if m:
            return str(
                self._hash_do(
                    id, idx, int(m.group(3)), int(m.group(2)), hash_type=m.group(1)
                )
            )

        # Example: H/15 -> 7-59/15 (i.e. 7,22,37,52)
        m = re.match(r"^(H|R)\/(\d+)$", item)
        if m:
            return "{}-{}/{}".format(
                self._hash_do(id, idx, int(m.group(2)), hash_type=m.group(1)),
                self.RANGES[idx][1],
                int(m.group(2)),
            )

        # Everything else
        return item
