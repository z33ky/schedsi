PREFIX=/usr
DESTDIR=/

PY_SOURCES=schedsi example tests replay.py plot.py

example: .PHONY
	PYTHONPATH=. example/kernel.py|PYTHONPATH=. ./replay.py -

text: .PHONY
	PYTHONPATH=. example/kernel.py|PYTHONPATH=. ./replay.py - --text

graph: .PHONY
	PYTHONPATH=. example/kernel.py|PYTHONPATH=. ./replay.py - --graph

test: .PHONY
	PYTHONPATH=. tests/example.py
	PYTHONPATH=. tests/simple.py
	PYTHONPATH=. tests/graph.py

update-docs:
	rm -f docs/source/schedsi.rst
	sphinx-apidoc -o docs/source schedsi

html: .PHONY
	$(MAKE) -C docs html

pylint: .PHONY
	pylint -r n $(PY_SOURCES)

pylint-disabled: .PHONY
	pylint -e fixme,locally-disabled $(PY_SOURCES)

build: .PHONY
	./setup.py build

install: .PHONY
	./setup.py install --prefix '$(PREFIX)' --root '$(DESTDIR)'

.PHONY:
