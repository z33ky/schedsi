#!/usr/bin/env python3
"""Functionality to create a :class:`Module`-hierarchy."""

from schedsi import module, threads

class ModuleBuilder:
    """Build static hierarchies."""

    def __init__(self, name="0", parent=None, *, scheduler):
        """Create a :class:`ModuleBuilder`."""
        self.module = module.Module(name, parent, scheduler)
        self.vcpus = []

    def add_module(self, name=None, *, scheduler, vcpus=1):
        """Attach a child :class:`Module`.

        The `name` is auto-generated, if it is `None`,
        as `self.name + "." + len(self.children)`.

        Returns the child-:class:`Module`.
        """
        if name is None:
            name = self.module.name + "." + str(self.module.num_children())
        madder = ModuleBuilder(name, self.module, scheduler=scheduler)
        self.vcpus.append((madder.module, vcpus))
        return madder

    def add_thread(self, thread, *args, **kwargs):
        """Add a :class:`Thread`.

        `thread` is the class.
        All parameters are forwarded to the init-function.

        Returns `self`.
        """
        self.module.add_thread(thread(self.module, *args, **kwargs))
        return self

    def add_vcpus(self):
        """Create all VCPUs for the attached children.

        VCPUs can be added incrementally while attaching modules.

        Returns `self`.
        """
        for child, vcpus in self.vcpus:
            for _ in range(0, vcpus):
                self.add_thread(threads.VCPUThread, child=child)
        self.vcpus.clear()
        return self
