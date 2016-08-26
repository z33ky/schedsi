#!/usr/bin/env python3
"""Thread classes."""

class Thread: # pylint: disable=too-few-public-methods
    """The basic thread class.

    A thread has
        * an associated module
        * a locally unique thread id
        * a start_time (when the thread can execute something) (-1 if finished)
        * remaining workload (-1 if infinite)
        * last deschedule time (-1 if never)
        * total runtime
        * total waittime
    """

    def __init__(self, module, tid, start_time, units):
        """Create a thread."""
        self.module = module
        self.tid = tid
        self.start_time = start_time
        self.remaining = units
        self.last_deschedule = -1
        self.total_run_time = 0
        self.total_wait_time = 0

    def execute(self, cpu, run_time=None):
        """Simulate execution.

        The thread will run for as long as it can.

        The remaining timeslice is returned.
        """
        assert self.start_time != -1 and self.start_time <= cpu.status.current_time
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
            self.start_time = -1
        else:
            #not enough time to complete the job
            self.start_time = current_time

        return run_time

    def _update_timing_stats(self, wait_time, run_time, current_time):
        """Update total_wait_time, total_run_time, last_deschedule."""
        self.total_wait_time += wait_time
        self.total_run_time += run_time
        self.last_deschedule = current_time

class SchedulerThread(Thread): # pylint: disable=too-few-public-methods
    """A thread representing a VCPU for a child.

    When this thread should execute,
    the scheduler for the child will be called.

    self.last_deschedule and self.total_wait_time is not meaningful.
    """
    def __init__(self, tid, scheduler):
        """Create a scheduler thread."""
        super().__init__(scheduler.module, tid, scheduler.next_start_time(), -1)
        self.scheduler = scheduler

    def execute(self, cpu): # pylint: disable=arguments-differ
        """Simulate execution.

        Simply forward to the scheduler.
        """
        run_time = self.scheduler.schedule(cpu) # pylint: disable=not-callable
        self.start_time = self.scheduler.next_start_time()
        self.total_run_time += run_time
        return run_time

    def add_threads(self, new_threads):
        """Add threads to scheduler."""
        self.scheduler.threads += new_threads
        self.start_time = self.scheduler.next_start_time()

class VCPUThread(Thread): # pylint: disable=too-few-public-methods
    """A thread representing a VCPU from the perspective of a parent.

    When this thread should execute,
    a SchedulerThread for a child will be called.
    """
    def __init__(self, module, tid, child):
        """Create a VCPUThread."""
        if child.parent != module:
            print(module.name, "is adding a VCPUThread for", child,
                  "although it is not a direct descendant.")
        child_thread = child.register_vcpu(self)
        super().__init__(module, tid, child_thread.start_time, child_thread.remaining)
        self._thread = child_thread
        if not isinstance(self._thread, SchedulerThread):
            print("VCPUThread expected a SchedulerThread, got", type(self._thread).__name__, ".")

    def execute(self, cpu): # pylint: disable=arguments-differ
        """Simulate execution.

        Switch context and forward to child thread.
        """
        run_time = cpu.switch_module(self._thread.module)
        run_time += self._thread.execute(cpu)

        self.update_child_state()

        run_time += cpu.switch_module(self.module)

        current_time = cpu.status.current_time
        self._update_timing_stats(current_time - run_time, run_time, current_time)

        return run_time

    def update_child_state(self):
        """Update start_time.

        This has to be called after the child's threads change
        to reflect their new requirements.
        """
        self.start_time = self._thread.start_time
        self.remaining = self._thread.remaining

class PeriodicWorkThread(Thread): # pylint: disable=too-few-public-methods
    """A thread needing periodic bursts of CPU."""
    def __init__(self, module, tid, start_time, units, period, burst):
        """Create a periodic work thread."""
        if period < burst:
            raise RuntimeError('Holy shit')
        super().__init__(module, tid, start_time, units)
        self.original_start_time = self.start_time
        self.period = period
        self.burst = burst

    #will run as long as the summed up bursts require
    def execute(self, cpu): # pylint: disable=arguments-differ
        """Simulate execution."""
        #how often we wanted to be executed (including this one)
        activations = int((cpu.status.current_time - self.original_start_time) / self.period) + 1
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
                #set start_time to next burst arrival
                self.start_time = self.original_start_time + activations * self.period

        return run_time
