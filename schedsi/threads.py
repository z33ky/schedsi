#!/usr/bin/env python3
"""Thread classes."""

class Thread: # pylint: disable=too-few-public-methods
    """The basic thread class.

    A thread has
        * an associated module
        * a locally unique thread id
        * ready time (-1 if finished)
        * remaining workload (-1 if infinite)
        * last deschedule time (-1 if never)
        * total runtime
        * total waittime
    """

    def __init__(self, module, tid, ready_time, units):
        """Create a :class:`Thread`."""
        self.module = module
        self.tid = tid
        self.ready_time = ready_time
        self.remaining = units
        self.last_deschedule = -1
        self.total_run_time = 0
        self.total_wait_time = 0

    def execute(self, cpu, run_time=None):
        """Simulate execution.

        The thread will run for as long as it can.

        The time spent executing is returned.
        """

        assert self.ready_time != -1 and self.ready_time <= cpu.status.current_time
        assert self.remaining == -1 or self.remaining > 0

        if not run_time is None:
            #only a sub-class is allowed to pass run_time
            assert self.execute != Thread.execute
        if run_time is None or (run_time > self.remaining and self.remaining != -1):
            run_time = self.remaining

        run_time = cpu.crunch(self, run_time)
        if run_time == 0:
            return 0

        current_time = cpu.status.current_time

        self._update_timing_stats(current_time - run_time, run_time, current_time)

        if self.remaining != -1:
            self.remaining -= run_time
            assert self.remaining >= 0

        if self.remaining == 0:
            #the job was completed within the slice
            #never start again
            self.ready_time = -1
        else:
            #not enough time to complete the job
            self.ready_time = current_time

        return run_time

    def _update_timing_stats(self, wait_time, run_time, current_time):
        """Update total_wait_time, total_run_time, last_deschedule."""
        self.total_wait_time += wait_time
        self.total_run_time += run_time
        self.last_deschedule = current_time

class SchedulerThread(Thread): # pylint: disable=too-few-public-methods
    """A thread representing a VCPU for a child.

    Execution is forwarded to the scheduler of the child :class:`Module`.
    """

    def __init__(self, tid, scheduler):
        """Create a :class:`SchedulerThread`."""
        super().__init__(scheduler.module, tid, scheduler.next_ready_time(), -1)
        self.scheduler = scheduler

    def execute(self, cpu): # pylint: disable=arguments-differ
        """Simulate execution.

        Simply forward to the scheduler.

        See :meth:`Thread.execute`.
        """
        run_time = self.scheduler.schedule(cpu) # pylint: disable=not-callable
        self.ready_time = self.scheduler.next_ready_time()
        self.total_run_time += run_time
        return run_time

    def add_threads(self, new_threads):
        """Add threads to scheduler."""
        self.scheduler.threads += new_threads
        self.ready_time = self.scheduler.next_ready_time()

class VCPUThread(Thread): # pylint: disable=too-few-public-methods
    """A thread representing a VCPU from the perspective of a parent.

    Execution is forwarded to the :class:`SchedulerThread` of the child.
    """

    def __init__(self, module, tid, child):
        """Create a :class:`VCPUThread`."""
        if child.parent != module:
            print(module.name, "is adding a VCPUThread for", child,
                  "although it is not a direct descendant.")
        child_thread = child.register_vcpu(self)
        super().__init__(module, tid, child_thread.ready_time, child_thread.remaining)
        self._thread = child_thread
        if not isinstance(self._thread, SchedulerThread):
            print("VCPUThread expected a SchedulerThread, got", type(self._thread).__name__, ".")

    def execute(self, cpu): # pylint: disable=arguments-differ
        """Simulate execution.

        Switch context and forward to child thread.

        See :meth:`Thread.execute`.
        """
        run_time = cpu.switch_module(self._thread.module)
        run_time += self._thread.execute(cpu)
        run_time += cpu.switch_module(self.module)

        current_time = cpu.status.current_time
        self._update_timing_stats(current_time - run_time, run_time, current_time)

        return run_time

    def __getattribute__(self, key):
        """ready_time and remaining should be taken from the SchedulerThread."""
        if key in ['ready_time', 'remaining']:
            return self._thread.__getattribute__(key)
        return object.__getattribute__(self, key)

class PeriodicWorkThread(Thread): # pylint: disable=too-few-public-methods
    """A thread needing periodic bursts of CPU."""

    def __init__(self, module, tid, ready_time, units, period, burst):
        """Create a :class:`PeriodicWorkThread`."""
        if period < burst:
            raise RuntimeError('Holy shit')
        super().__init__(module, tid, ready_time, units)
        self.original_ready_time = self.ready_time
        self.period = period
        self.burst = burst

    #will run as long as the summed up bursts require
    def execute(self, cpu): # pylint: disable=arguments-differ
        """Simulate execution.

        See :meth:`Thread.execute`.
        """
        #how often we wanted to be executed (including this one)
        activations = int((cpu.status.current_time - self.original_ready_time) / self.period) + 1
        quota = activations * self.burst

        if quota < 0:
            raise RuntimeError('Scheduled too eagerly')
        quota_left = quota - self.total_run_time
        if quota_left < 0:
            raise RuntimeError('Executed too much')

        run_time = super().execute(cpu, quota_left)

        assert run_time <= quota_left
        if self.remaining > 0 or self.remaining == -1:
            if quota_left == run_time:
                #set ready_time to next burst arrival
                self.ready_time = self.original_ready_time + activations * self.period

        return run_time
