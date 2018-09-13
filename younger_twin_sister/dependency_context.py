import os

from younger_twin_sister.dependency_registry import DependencyRegistry
import younger_twin_sister.fake_fs as fake_fs
from younger_twin_sister.fake_singleton import FakeSingleton
from younger_twin_sister.singleton_class import SingletonClass


class Passthrough:

    def __init__(self, target):
        self._target = target

    def __getattr__(self, name):
        return getattr(self._target, name)


class DependencyContext:

    def __init__(self, *, parent=None, supply_env=False, supply_fs=False):
        """
        parent -- Inherit dependencies injected into this context
        """
        self._attached_threads = []
        self._injected = []  # key/value tuples
        self._parent = parent
        self.fs = None
        self.os = Passthrough(os)
        if supply_fs:
            self._supply_fs()
        if supply_env:
            self._supply_env()
        self.inject(os, self.os)

    def _supply_fs(self):
        self.fs = fake_fs.create_fs()
        self.os = fake_fs.create_os(self.fs)
        self.inject(os.path, self.os.path)
        self.inject(open, fake_fs.create_open(self.fs))

    def _supply_env(self):
        self.os.environ = {}

    def attach_to_thread(self, thread_object):
        """
        Attach this context to a thread.
        After attachment, calls to "dependency" inside the thread
          will use this context.

        thread_object -- (Thread) Attach to this thread
        """
        thread_id = thread_object.ident
        if not thread_id:
            raise RuntimeError('A running thread is required.')
        DependencyRegistry.register(
            context=self, thread_id=thread_id)
        self._attached_threads.append(thread_id)

    def close(self):
        for t in self._attached_threads:
            DependencyRegistry.unregister(self, thread_id=t)
        DependencyRegistry.unregister(self)

    def get(self, dependency):
        for k, v in self._injected:
            if k == dependency:
                return v
        if self._parent:
            return self._parent.get(dependency)
        return dependency

    def inject(self, dependency, injected):
        self._injected = [
            (k, v) for k, v in self._injected
            if k != dependency]
        self._injected.append((dependency, injected))

    def inject_as_class(self, dependency, injected):
        """
        Inject an object as though it were a class.
        When the victim requests the class, the injector returns
        a SingletonClass which wraps the injected object.
        """
        self.inject(dependency, SingletonClass(injected))

    def inject_as_singleton(self, dependency, injected):
        """
        Inject as an object as though it were a singleton.
        When the victim requests the class, the injector returns an object
        with an "instance" method which returns the injected object.
        """
        self.inject(dependency, FakeSingleton(injected))

    def create_file(self, filename, *, content=None, text=None):
        """
        Create a file in the fake filesystem
        filename -- (str) Full path to the new file
        content -- (byte sequence) Write this binary content
        text -- (str) Write this text content
        """
        if content and text:
            raise TypeError('Content and text cannot both be specified')
        path, _ = self.os.path.split(filename)
        self.os.makedirs(path, exist_ok=True)
        fd = self.os.open(filename, self.os.O_CREAT | self.os.O_WRONLY)
        if content or text:
            bytes_out = content or bytes(text, encoding='utf-8')
            self.os.write(fd, bytes_out)
        self.os.close(fd)
