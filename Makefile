PREFIX=/usr
DESTDIR=/

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

html: .PHONY
	$(MAKE) -C docs html

pylint: .PHONY
	pylint -r n schedsi example tests replay.py

pylint-disabled: .PHONY
	pylint -e locally-disabled schedsi example tests replay.py

build: .PHONY
	./setup.py build

install: .PHONY
	./setup.py install --prefix '$(PREFIX)' --root '$(DESTDIR)'

.PHONY:
