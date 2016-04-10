MARKDOWN=dsari-daemon.md dsari-render.md dsari-info.md
MAN=$(patsubst %.md,%.1,$(MARKDOWN)) 

all: man
man: ${MAN}

clean: 
	rm -f ${MAN}

%.1: %.md
	pandoc -s -t man -o $@ $<
