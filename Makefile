PYTHON = python

check:
	$(PYTHON) -m unittest buildfarm.tests.test_suite
