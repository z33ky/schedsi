#!/usr/bin/env python3
"""Defines a Round Robin scheduler."""

def scheduler(module, cpu, current_time, timer_quantum, log):
    """Schedule the next thread of module.

    The remaining timeslice is returned.
    """
    #HACK
    data = module.scheduler.scheduler_data
    num_threads = len(module.threads)

    if num_threads == 0:
        log.schedule_none(cpu, current_time, module)
        return timer_quantum

    thread = None
    idx = data.next_idx
    last_idx = idx - 1 if idx != 0 else num_threads - 1
    while True:
        thread = module.threads[idx]
        if thread.starttime >= 0 and thread.starttime <= current_time:
            break
        if idx == last_idx:
            #tried all threads, but no thread ready
            log.schedule_none(cpu, current_time, module)
            return timer_quantum

        idx = idx + 1 if idx != num_threads - 1 else 0

    data.next_idx = idx + 1 if idx != num_threads - 1 else 0

    #cost for context switch
    cost = 0 if module == thread.module else 1
    if timer_quantum < cost:
        #not enough time to do the switch
        log.schedule_thread_fail(cpu, current_time, module, timer_quantum)
        return 0

    log.schedule_thread(cpu, current_time, thread, cost)
    timer_quantum -= cost
    current_time += cost

    left = thread.execute(cpu, current_time, timer_quantum, log)
    if left < 0:
        raise RuntimeError('Executed too much')
    if left == 0:
        return 0

    current_time += timer_quantum - left

    #thread yielded
    #context switch back to parent
    if left < cost:
        #not enough time to do the switch
        log.schedule_thread_fail(cpu, current_time, module, left)
        return 0

    left -= cost
    current_time += cost
    return scheduler(module, cpu, current_time, left, log)

class SchedulerData: # pylint: disable=too-few-public-methods
    """State for the scheduler."""
    def __init__(self):
        self.next_idx = 0

def init_scheduler_thread(thread):
    """Set this as the scheduler for the SchedulerThread."""
    thread.scheduler = scheduler
    thread.scheduler_data = SchedulerData()
