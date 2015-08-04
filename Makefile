all: build

build:
	python setup.py build

install: build
	python setup.py install

clean:
	python setup.py clean
	$(RM) -r build MANIFEST

doc: README
	$(MAKE) -C doc

README: README.md
	pandoc -s -t plain -o $@ $<
