"""Public-data source modules.

Each module exposes one or more `collect_*(project, ...) -> list[MetricPoint]
| list[Event]` functions. There's no shared base class across them — a PyPI
package name and a GitHub owner/repo pair don't share enough shape to make
one useful. The common interface (per the spec) is instead: the same error
types and the same JSON-over-HTTP plumbing (`hirogari.sources.base`), and
the same "identify the target, get back typed store records" function
shape, so `cli.py` can call any of them uniformly and handle failures the
same way regardless of which source raised.
"""
