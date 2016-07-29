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

    def execute(self, cpu, current_time, run_time, log):
        """Simulate execution.

        The thread will run for as long as it can.

        The remaining timeslice is returned.
        """

        self.total_wait_time += current_time - self.start_time

        if self.remaining > run_time or self.remaining == -1:
            #not enough time to complete the job
            self.total_run_time += run_time
            log.thread_execute(cpu, current_time, self, run_time)
            self.remaining -= run_time
            current_time += run_time
            self.start_time = self.last_deschedule = current_time
            return 0
        else:
            #the job will be complete in the time
            log.thread_execute(cpu, current_time, self, self.remaining)
            run_time -= self.remaining
            current_time += self.remaining
            self.remaining = 0
            #never start again
            self.start_time = -1
            #a.k.a. finished_time
            self.last_deschedule = current_time
            log.thread_yield(cpu, current_time, self)
            return run_time

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

    def execute(self, cpu, current_time, run_time, log):
        """Simulate execution.

        Simply forward to the scheduler.
        """
        left = self.scheduler.schedule(cpu, current_time, run_time, log) # pylint: disable=not-callable
        self.start_time = self.scheduler.next_start_time()
        self.total_run_time += current_time - left
        return left

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

    def execute(self, cpu, current_time, run_time, log):
        """Simulate execution.

        Switch context and forward to child thread.
        """
        #cost for context switch
        cost = 0 if self.module == self._thread.module else 1
        if run_time < cost:
            #not enough time to do the switch
            log.context_switch_fail(cpu, current_time, self._thread.module, self.module, run_time)
            return 0

        log.context_switch(cpu, current_time, self.module, self._thread.module, cost)
        run_time -= cost
        current_time += cost

        left = self._thread.execute(cpu, current_time, run_time, log)
        self.update_child_state()
        self.remaining = self._thread.remaining
        elapsed = run_time - left
        self.total_run_time += elapsed
        current_time += elapsed

        #thread yielded
        if left == 0:
            return 0
        #context switch back to parent
        if left < cost:
            #not enough time to do the switch
            log.context_switch_fail(cpu, current_time, self._thread.module, self.module, left)
            return 0

        left -= cost

        return left

    def update_child_state(self):
        """Update start_time.

        This has to be called after the child's threads change
        to reflect their new requirements.
        """
        self.start_time = self._thread.start_time

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
    def execute(self, cpu, current_time, run_time, log):
        """Simulate execution."""
        #how often we wanted to be executed (including this one)
        activations = int((current_time - self.original_start_time) / self.period) + 1
        quota = activations * self.burst

        if quota < 0:
            raise RuntimeError('Scheduled too eagerly')
        quota_left = quota - self.total_run_time
        if quota_left < 0:
            raise RuntimeError('Executed too much')

        exec_time = quota_left if quota_left <= run_time else run_time

        left = run_time - exec_time + super().execute(cpu, current_time, exec_time, log)

        if left > 0 and self.remaining > 0:
            if exec_time < quota_left:
                raise RuntimeError('Executed too little')
            self.start_time = self.original_start_time + activations * self.period

        return left
