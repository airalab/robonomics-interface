# robonomics-interface
This is a simple wrapper over https://github.com/polkascan/py-substrate-interface used to facilitate writing code for applications using Robonomics.

Robonomics project: https://robonomics.network/

Robonomics parachain dapp: https://parachain.robonomics.network/

Documentation: https://multi-agent-io.github.io/robonomics-interface/
_______
# Installation 
```bash
pip3 install robonomics-interface
```
# Contributing

When contributing to this repository, please first discuss the change you wish to make via issue,
email, or any other method with the owners of this repository before making a change. 

## Pull Request Process

1. Install [poetry](https://python-poetry.org/docs/) 
2. Git clone the repository
3. Install requirements with
```bash
poetry install
```
Installing `substrate_interface` may require [Rust](https://www.rust-lang.org/tools/install) and 
[Rustup nightly](https://rust-lang.github.io/rustup/concepts/channels.html).

4. Add functions/edit code/fix issues.
5. Make a PR.
6. ...
7. Profit!


## Some important rules
- If needed, install dependencies with
```bash
poetry add <lib>
```
- Use `ReStructuredText` docstrings.
- Respect typing annotation.
- Add documentation. Please take in consideration that if a new class was created, add it to `docs/source/modules.rst`.
Other functionality is better to be described in `docs/source/usage.rst`
- Black it:
```bash
black -l 120 <modified_file>
```
- Check how the docs look via `make html` from the `docs` folder and checking the `docs/build/html/index.html` page.
- Do not bump version.
- One may test the code by
```bash
# in project root
poetry build
pip3 uninstall robonomcis_interface -y  #if was installed previously
pip3 install pip3 install dist/robonomics_interface-<version>-py3-none-any.whl 
python3 <testing_script>
```