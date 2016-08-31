example: .PHONY
	PYTHONPATH=. example/kernel.py|PYTHONPATH=. ./replay.py -

text: .PHONY
	PYTHONPATH=. example/kernel.py|PYTHONPATH=. ./replay.py - --text

graph: .PHONY
	PYTHONPATH=. example/kernel.py|PYTHONPATH=. ./replay.py - --graph

test: .PHONY
	PYTHONPATH=. tests/example.py
	PYTHONPATH=. tests/simple.py

html: .PHONY
	$(MAKE) -C docs html

pylint: .PHONY
	pylint schedsi example tests replay.py

.PHONY:
