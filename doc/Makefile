# SPDX-PackageName: dsari
# SPDX-PackageSupplier: Ryan Finnie <ryan@finnie.org>
# SPDX-PackageDownloadLocation: https://forge.colobox.com/rfinnie/dsari
# SPDX-FileCopyrightText: © 2015 Ryan Finnie <ryan@finnie.org>
# SPDX-License-Identifier: MPL-2.0

MARKDOWN=dsari-daemon.md dsari-info.md dsari-prometheus-exporter.md dsari-render.md
MAN=$(patsubst %.md,%.1,$(MARKDOWN))

all: man
man: ${MAN}

clean:
	rm -f ${MAN}

%.1: %.md
	pandoc -s -t man -o $@ $<
