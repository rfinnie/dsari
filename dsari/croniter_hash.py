#!/usr/bin/env python3

# croniter_hash - Extend croniter with hash/random support
# Copyright (C) 2015-2018 Ryan Finnie
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
import random


class croniter_hash(croniter.croniter):
    def __init__(self, expr_format, *args, **kwargs):
        if 'hash_id' in kwargs:
            if kwargs['hash_id']:
                expr_format = self._hash_expand(expr_format, kwargs['hash_id'])
            del(kwargs['hash_id'])
        return super(croniter_hash, self).__init__(expr_format, *args, **kwargs)

    def _hash_do(self, id, position, range_end=None, range_begin=None, type='H'):
        if not range_end:
            range_end = self.RANGES[position][1]
        if not range_begin:
            range_begin = self.RANGES[position][0]
        if type == 'R':
            crc = random.randint(0, 0xffffffff)
        else:
            crc = binascii.crc32(id.encode('utf-8')) & 0xffffffff
        return ((crc >> position) % (range_end - range_begin + 1)) + range_begin

    def _hash_expand(self, expr_format, id):
        if expr_format == '@midnight':
            expr_format = 'H H(0-2) * * * H'
        elif expr_format == '@hourly':
            expr_format = 'H * * * * H'
        elif expr_format == '@daily':
            expr_format = 'H H * * * H'
        elif expr_format == '@weekly':
            expr_format = 'H H * * H H'
        elif expr_format == '@monthly':
            expr_format = 'H H H * * H'
        elif expr_format == '@annually':
            expr_format = 'H H H H * H'
        elif expr_format == '@yearly':
            expr_format = 'H H H H * H'

        expr_expanded = []
        for item in expr_format.split(' '):
            idx = len(expr_expanded)
            expr_expanded.append(self._hash_expand_item(item, id, idx))
        return ' '.join(expr_expanded)

    def _hash_expand_item(self, item, id, idx):
        # Example: H -> 32
        if item in ('H', 'R'):
            return str(self._hash_do(id, idx, type=item))

        # Example: H(30-59)/10 -> 34-59/10 (i.e. 34,44,54)
        m = re.match('^(H|R)\((\d+)-(\d+)\)\/(\d+)$', item)
        if m:
            return '{}-{}/{}'.format(
                self._hash_do(
                    id, idx, int(m.group(4)), type=m.group(1)
                ) + int(m.group(2)),
                int(m.group(3)),
                int(m.group(4))
            )

        # Example: H(0-29) -> 12
        m = re.match('^(H|R)\((\d+)-(\d+)\)$', item)
        if m:
            return str(
                self._hash_do(
                    id, idx, int(m.group(3)), int(m.group(2)), type=m.group(1)
                )
            )

        # Example: H/15 -> 7-59/15 (i.e. 7,22,37,52)
        m = re.match('^(H|R)\/(\d+)$', item)
        if m:
            return '{}-{}/{}'.format(
                self._hash_do(
                    id, idx, int(m.group(2)), type=m.group(1)
                ),
                self.RANGES[idx][1],
                int(m.group(2))
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
    print(iter.exprs)
    print(iter.expanded)
    for i in range(10):
        print(iter.get_next(datetime))
