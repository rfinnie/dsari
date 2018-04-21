MARKDOWN=dsari-daemon.md dsari-info.md dsari-prometheus-exporter.md dsari-render.md
MAN=$(patsubst %.md,%.1,$(MARKDOWN)) 

all: man
man: ${MAN}

clean: 
	rm -f ${MAN}

%.1: %.md
	pandoc -s -t man -o $@ $<
