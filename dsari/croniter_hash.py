#!/usr/bin/env python

# croniter_hash - Extend croniter with hash support
# Copyright (C) 2015 Ryan Finnie
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.

import binascii
import re
import croniter


class croniter_hash(croniter.croniter):
    def __init__(self, expr_format, *args, **kwargs):
        if 'hash_id' in kwargs:
            if kwargs['hash_id']:
                expr_format = self._hash_expand(expr_format, kwargs['hash_id'])
            del(kwargs['hash_id'])
        return super(croniter_hash, self).__init__(expr_format, *args, **kwargs)

    def _hash_do(self, id, position, range_end=None, range_begin=None):
        if not range_end:
            range_end = self.RANGES[position][1]
        if not range_begin:
            range_begin = self.RANGES[position][0]
        crc = binascii.crc32(id) & 0xffffffff
        return ((crc >> position) % (range_end - range_begin + 1)) + range_begin

    def _hash_expand(self, expr_format, id):
        expr_expanded = []
        for item in expr_format.split(' '):
            idx = len(expr_expanded)
            expr_expanded.append(self._hash_expand_item(item, id, idx))
        return ' '.join(expr_expanded)

    def _hash_expand_item(self, item, id, idx):
        # Example: H -> 32
        if item == 'H':
            return str(self._hash_do(id, idx))

        # Example: H(30-59)/10 -> 34-59/10 (i.e. 34,44,54)
        m = re.match('^H\((\d+)-(\d+)\)\/(\d+)$', item)
        if m:
            return '%d-%d/%d' % (
                self._hash_do(
                    id, idx, int(m.group(3))
                ) + int(m.group(1)),
                int(m.group(2)),
                int(m.group(3))
            )

        # Example: H(0-29) -> 12
        m = re.match('^H\((\d+)-(\d+)\)$', item)
        if m:
            return str(
                self._hash_do(
                    id, idx, int(m.group(2)), int(m.group(1))
                )
            )

        # Example: H/15 -> 7-59/15 (i.e. 7,22,37,52)
        m = re.match('^H\/(\d+)$', item)
        if m:
            return '%d-%d/%d' % (
                self._hash_do(
                    id, idx, int(m.group(1))
                ),
                self.RANGES[idx][1],
                int(m.group(1))
            )

        # Everything else
        return item


if __name__ == '__main__':
    from datetime import datetime
    import random
    import string
    id = 'foo'
    id = ''.join(
        random.choice(string.ascii_letters + string.digits)
        for i in range(30)
    )
    base = datetime.now()
    iter = croniter_hash('1 2 * * *', base)
    iter = croniter_hash('3 4 * * *', base, hash_id=id)
    iter = croniter_hash('H(30-59)/10 H(2-5) H/3 H *', base, hash_id=id)
    print iter.exprs
    print iter.expanded
    for i in xrange(10):
        print iter.get_next(datetime)
