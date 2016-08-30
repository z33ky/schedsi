example: .PHONY
	PYTHONPATH=. example/kernel.py

test: .PHONY
	PYTHONPATH=. tests/example.py
	PYTHONPATH=. tests/simple.py

pylint: .PHONY
	pylint schedsi example tests replay.py

.PHONY:
