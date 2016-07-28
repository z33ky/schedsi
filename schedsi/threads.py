#!/usr/bin/env python3
"""Thread classes."""

class Thread: # pylint: disable=too-few-public-methods
    """The basic thread class.

    A thread has
        * an associated module
        * a locally unique thread id
        * a starttime (when the thread can execute something) (-1 if finished)
        * remaining workload (-1 if infinite)
        * last deschedule time (-1 if never)
        * total runtime
        * total waittime
    """

    def __init__(self, module, tid, starttime, units):
        """Create a thread."""
        self.module = module
        self.tid = tid
        self.starttime = starttime
        self.remaining = units
        self.last_deschedule = -1
        self.total_run_time = 0
        self.total_wait_time = 0

    def execute(self, cpu, current_time, run_time, log):
        """Simulate execution.

        The thread will run for as long as it can.

        The remaining timeslice is returned.
        """

        self.total_wait_time += current_time - self.starttime

        if self.remaining >= run_time or self.remaining == -1:
            self.total_run_time += run_time
            log.thread_execute(cpu, current_time, self, run_time)
            self.remaining -= run_time
            current_time += run_time
            self.starttime = self.last_deschedule = current_time
            return 0
        else:
            log.thread_execute(cpu, current_time, self, self.remaining)
            run_time -= self.remaining
            current_time += self.remaining
            self.remaining = 0
            #never start again
            self.starttime = -1
            log.thread_yield(cpu, current_time, self)
            return run_time

class SchedulerThread(Thread): # pylint: disable=too-few-public-methods
    """A thread representing a VCPU for a child.

    When this thread should execute,
    the scheduler for the child will be called.

    self.last_deschedule and self.total_wait_time is not meaningful.
    """
    def __init__(self, module, tid, starttime, scheduler):
        """Create a scheduler thread."""
        super().__init__(module, tid, starttime, -1)
        self.scheduler = None
        self.scheduler_data = None
        scheduler.init_scheduler_thread(self)
        if self.scheduler is None:
            raise RuntimeError('Scheduler didn\'t set itself')

    def execute(self, cpu, current_time, run_time, log):
        """Simulate execution.

        Simply forward to the scheduler.
        """
        left = self.scheduler(self.module, cpu, current_time, run_time, log) # pylint: disable=not-callable
        self.total_run_time += current_time - left
        return left

class PeriodicWorkThread(Thread): # pylint: disable=too-few-public-methods
    """A thread needing periodic bursts of CPU."""
    def __init__(self, module, tid, starttime, units, period, burst):
        """Create a periodic work thread."""
        if period < burst:
            raise RuntimeError('Holy shit')
        super().__init__(module, tid, starttime, units)
        self.original_starttime = self.starttime
        self.period = period
        self.burst = burst

    #will run as long as the summed up bursts require
    def execute(self, cpu, current_time, run_time, log):
        """Simulate execution."""
        #how often we wanted to be executed (including this one)
        activations = int((current_time - self.original_starttime) / self.period) + 1
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
            self.starttime = self.original_starttime + activations * self.period

        return left
