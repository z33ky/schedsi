PREFIX=/usr
DESTDIR=/

PY_SOURCES=schedsi example tests replay.py plot.py

example-lt: .PHONY
	PYTHONPATH=. example/localtimer_kernel.py|PYTHONPATH=. ./replay.py -

example-st: .PHONY
	PYTHONPATH=. example/singletimer_kernel.py|PYTHONPATH=. ./replay.py -

example-pen: .PHONY
	PYTHONPATH=. example/penalty_scheduler.py|PYTHONPATH=. ./replay.py -

example: .PHONY example-lt

text-lt: .PHONY
	PYTHONPATH=. example/localtimer_kernel.py|PYTHONPATH=. ./replay.py - --text

text-st: .PHONY
	PYTHONPATH=. example/singletimer_kernel.py|PYTHONPATH=. ./replay.py - --text

text-pen: .PHONY
	PYTHONPATH=. example/penalty_scheduler.py|PYTHONPATH=. ./replay.py - --text

graph-lt: .PHONY
	PYTHONPATH=. example/localtimer_kernel.py|PYTHONPATH=. ./replay.py - --graph

graph-st: .PHONY
	PYTHONPATH=. example/singletimer_kernel.py|PYTHONPATH=. ./replay.py - --graph

graph-pen: .PHONY
	PYTHONPATH=. example/penalty_scheduler.py|PYTHONPATH=. ./replay.py - --graph

test: .PHONY
	PYTHONPATH=. tests/examples.py
	PYTHONPATH=. tests/simple.py
	PYTHONPATH=. tests/graphs.py
	PYTHONPATH=. tests/schedsim.py

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
