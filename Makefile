PYTHON:=python3

all: build

build:
	$(PYTHON) setup.py build

install: build
	$(PYTHON) setup.py install

clean:
	$(PYTHON) setup.py clean
	$(RM) -r build MANIFEST

doc: README
	$(MAKE) -C doc

README: README.md
	pandoc -s -t plain -o $@ $<
