.PHONY: clean update install develop devel docs tests test release

test: tests

clean:
	rm -rvf *.egg-info
	rm -rvf build
	rm -rvf dist
	find . -iname \*.pyo -exec rm -vf {} \;
	find . -iname \*.pyc -exec rm -vf {} \;
	find . -iname \*.so -exec rm -vf {} \;
	rm -rvf docs/build

update:
	git pull origin master

install:
	python setup.py install

develop:
	cp -f setup.cfg-devel setup.cfg
	python setup.py develop

devel: develop

docs:
	@mkdir -p docs/build/html
	sphinx-build -b html -d docs/build/doctrees docs/source build/html

.testing-deps:
	pip install -q nose coverage
	pip install git+git://github.com/exogen/nose-achievements.git
	@touch .testing-deps

tests: .testing-deps
	python setup.py nosetests

release: tests docs
	cp -f setup.cfg-release setup.cfg
	python setup.py register sdist bdist_egg upload upload_docs
	cp -f setup.cfg-devel setup.cfg
