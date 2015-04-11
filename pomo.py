#!/usr/bin/env python

# Author: Stefan van der Walt <stefan@sun.ac.za>
# License: BSD


import argparse, time, os, warnings, itertools, collections, \
       datetime, sys, threading, multiprocessing, queue, copy

TASK_DURATION = 1500
APP_PATH = os.path.dirname(os.path.realpath(__file__))
SOUND_DONE = os.path.abspath(os.path.join(APP_PATH, 'sounds', 'pop.ogg'))

parser = argparse.ArgumentParser(description='Pomodoro timer')
parser.add_argument('-m', '--message', type=str,
                    help='description of task to work on')
parser.add_argument('-t', '--time', type=int,
                    help='intended duration of task')
parser.add_argument('-o', '--ondone', type=str,
                    help='command to execute when the current task is done')
parser.add_argument('-d', '--directory', type=str,
                    help='directory where logs will be written')
parser.add_argument('-s', '--split', dest='split', action='store_true',
                    help='split log files by day')
parser.set_defaults(split=False)
parser.add_argument('-c', '--continuous', dest='continuous', action='store_true',
                    help='work on tasks continuously')
parser.set_defaults(continuous=False)
parser.add_argument('-b', '--startbreak', dest='startbreak', action='store_true',
                    help='start a break before starting a task')
parser.set_defaults(startbreak=False)
parser.add_argument('-a', '--analyse', type=str,
                    help='analyse the given pomo log')
args = parser.parse_args()

if args.message is None and args.analyse is None:
    parser.print_help()
    print("\nEither specify a task, or analyse a log file.")
    sys.exit(-1)

if args.time is not None:
    TASK_DURATION = args.time

try:
    print('Checking for Notify...', end=' ')
    from gi.repository import Notify
    has_pynotify = True
    print('found.')
except ImportError:
    has_pynotify = False
    print('not found.')

try:
    print('Checking for appindicator...', end=' ')
    import appindicator
    has_appindicator = True
    print('found.')

    app_type = appindicator.CATEGORY_APPLICATION_STATUS
    app_status_active = appindicator.STATUS_ACTIVE
    app_status_attention = appindicator.STATUS_ATTENTION
except ImportError:
    print('not found.')
    has_appindicator = False
    app_type = None
    app_status_active = 1
    app_status_attention = 2

try:
    print('Checking for gtk...', end=' ')
    from gi.repository import Gtk
    from gi.repository import GObject
    has_gtk = True

    print('found.')
except ImportError:
    has_gtk = False
    print('not found.')

if has_gtk:
    class GTKIndicator(object):
        """Inspired by
        http://askubuntu.com/questions/13197/how-to-program-a-status-icon-that-will-display-in-ubuntu-11-04-as-well-as-in-othe/13206#13206

        and code released by George Edison under an MIT License.
        """
        def __init__(self, name, icon, status):
            self.icon = Gtk.StatusIcon()
            self.icon.set_from_file(
                os.path.join(os.path.dirname(__file__), './icons',
                             icon + '.png')
                )

        def set_menu(self, menu):
            self.menu = menu
            self.icon.connect("activate", self.show_menu)

        def show_menu(self, widget):
            self.menu.popup(None, None, None, 0, 0)

        def set_status(self, status):
            pass

        def set_attention_icon(self, icon):
            pass


if has_appindicator and has_gtk:
    Indicator = appindicator.Indicator
elif has_gtk:
    Indicator = GTKIndicator

def notify(title, message, sound=False):
    global has_pynotify

    if has_pynotify:
        if not Notify.init('pomo app'):
            has_pynotify = False

        n = Notify.Notification.new(title, message, 'pomo-applet-active')

        try:
            n.show()
        except:
            has_pynotify = False

    if not has_pynotify:
        print("\n\n" + "*" * 50)
        print(title)
        print(message)
        print("*" * 50 + "\n\n")

    if sound:
        os.system('gst-play-1.0 ' + SOUND_DONE + ' > /dev/null &')

def load_time(s):
    return datetime.datetime.strptime(s, '%Y/%m/%d %H:%M:%S')

def group(lst, n):
    """group([0,3,4,10,2,3], 2) => iterator

    Group an iterable into an n-tuples iterable. Incomplete tuples
    are discarded e.g.

    >>> list(group(range(10), 3))
    [(0, 1, 2), (3, 4, 5), (6, 7, 8)]

    http://code.activestate.com/recipes/
    303060-group-a-list-into-sequential-n-tuples/

    """
    return zip(
        *[itertools.islice(lst, i, None, n) for i in range(n)])

def report(data):
    data = [l.strip() for l in data]
    data = [l for l in data if l and not l.startswith('#')]

    L = len(data)
    if (L / 3) != (L // 3):
        print('Log file contains invalid number of lines. ')
        print('Trying to proceed anyway.')
        data = data[:L - (L % 3)]

    today = datetime.datetime.today().date()
    delta = datetime.timedelta(seconds=TASK_DURATION)

    pomos = collections.OrderedDict()
    total_today = datetime.timedelta()
    for (task, start, end) in group(data, 3):
        start = load_time(start)
        end = load_time(end)
        key = (task, end.date())

        if key not in pomos:
            pomos[key] = {'nr': 0,
                          'time': datetime.timedelta()}

        pomos[key]['nr'] += 1
        pomos[key]['time'] += delta

        if end.date() == today:
            total_today += delta


    # Combine tasks from different days
    join_tasks = collections.OrderedDict()
    for p in pomos:
        name, enddate = p
        if name not in join_tasks:
            join_tasks[name] = copy.copy(pomos[p])
        else:
            join_tasks[name]['nr'] += pomos[p]['nr']
            join_tasks[name]['time'] += pomos[p]['time']

    all_tasks = [(task, join_tasks[task]['nr']) for task in join_tasks]
    today_tasks = [(task, pomos[(task, end)]['nr']) for (task, end) in pomos \
                   if end == today]

    def print_tasks(tasks, header=''):
        total = sum(nr for (task, nr) in tasks)
        header = "%s [%d pomos]" % (header, total)

        print(header)
        print("-" * len(header))
        for task in tasks:
            print('%s [%d]' % task)
        print()

    print_tasks(all_tasks, "Summary: all tasks")
    print_tasks(today_tasks, "Summary: today's tasks")

    total = datetime.timedelta()
    longest_time = datetime.timedelta()
    longest_name = 'No task longer than 0 minutes'
    for (name, task) in list(join_tasks.items()):
        duration = task['time']
        total += task['time']

        if duration > longest_time:
            longest_time = duration
            longest_name = name

    print("Last 5 days")
    print("-----------")
    day_work = {}
    for (name, enddate), task in list(pomos.items()):
        days_ago = (today - enddate).days
        if days_ago <= 5:
            day_work[days_ago] = day_work.get(days_ago, 0) + task['nr']

    for i in range(5, -1, -1):
        if i in day_work:
            print(today - datetime.timedelta(days=i), "[%s]" % day_work[i])


    print("\nTime summary")
    print("------------")
    print("Total time for today:", total_today)
    print("Total time:", total)
    print("Longest task: %s at %s" % (longest_name, longest_time))


if args.analyse is not None:
    try:
        with open(args.analyse, 'r') as f:
            report(f.readlines())

    except IOError:
        print('Cannot load "%s" for analysis.' % args.analyse)
        sys.exit(-1)

    sys.exit(0)

class TimeConsumer(multiprocessing.Process):
    def __init__(self, time_queue, msg_queue):
        multiprocessing.Process.__init__(self)
        self.time_queue = time_queue
        self.msg_queue = msg_queue

    def run(self):
        while 1:
            task = self.time_queue.get()
            if task is None:
                break

            sys.stdout.write('Time left: ' + task + '\r')
            sys.stdout.flush()
            time.sleep(1)

        print()


class PomoApplet(TimeConsumer):
    def __init__(self, time_queue, msg_queue, task=""):
        TimeConsumer.__init__(self, time_queue, msg_queue)
        self.task = task
        self.time = '00:00'
        self._pause = False
        self._running = True

        loop = GObject.MainLoop()
        GObject.threads_init()
        self.context = loop.get_context()

    def run(self):
        ind = Indicator("pomo", "pomo-applet-active", app_type)
        ind.set_status(app_status_active)
        ind.set_attention_icon("pomo-applet-active")

        time_menu = Gtk.MenuItem("test")
        task_menu = Gtk.MenuItem('Task: ' + self.task)
        quit_menu = Gtk.MenuItem('Squish')
        pause_menu = Gtk.MenuItem('Pause/Unpause')

        quit_menu.connect("activate", self.squish)
        pause_menu.connect("activate", self.pause)

        menu = Gtk.Menu()
        for m in (time_menu,
                  task_menu,
                  Gtk.SeparatorMenuItem(),
                  quit_menu,
                  Gtk.SeparatorMenuItem(),
                  pause_menu):
            menu.append(m)
            m.show()

        ind.set_menu(menu)

        self._ind = ind
        self._menu = menu
        self._time_menu = time_menu

        self.update_label()

        while self._running:
            # Call GTK event loop
            self.flush_events()

            # Sleep shorter when in pause state, so that
            # counter will continue immediately when unpaused
            if self._pause:
                time.sleep(0.1)
                continue

            # Otherwise, consume a second-long job
            self.do_work_unit()

            sys.stdout.write('Time left: ' + self.time + '\r')
            sys.stdout.flush()


    def do_work_unit(self,):
        task = self.time_queue.get(timeout=1)
        if task is None:
            self.abort()
            return
        else:
            # Interrupt timer a number of times
            # to check for GTK events
            for i in range(20):
                time.sleep(1./20)
                self.flush_events()

        self.time = task
        self.update_label()

    def update_label(self):
        self._time_menu.set_label(self.time)
        self.flush_events()

    def squish(self, menu=None):
        self.msg_queue.put('ABORT')
        self.abort()

    def pause(self, menu=None):
        self._pause = not self._pause

    def abort(self):
        self._running = False

    def flush_events(self):
        while self.context.pending():
            self.context.iteration(True)
            time.sleep(0.01)


def launch_and_monitor(time_queue, msg_queue, task_name='', start_msg=None):
    if has_gtk:
        applet_process = PomoApplet(time_queue, msg_queue, task_name)
        applet_process.start()
    else:
        applet_process = TimeConsumer(time_queue, msg_queue)
        applet_process.start()

    # This has to be done after the GTK context has been created.
    # For some reason notify hijacks the GTK main loop, so
    # we can't use launch_and_monitor again after notifying.

    if start_msg is not None:
        notify(*start_msg)

    while applet_process.is_alive() or not msg_queue.empty():
        try:
            msg = msg_queue.get_nowait()
        except queue.Empty:
            time.sleep(0.1)
            msg = None

        if msg == 'ABORT':
            notify("Squish!",
                   'Tomato recycled...')
            applet_process.terminate()

    return applet_process

def start_task(restart=False):
    time_queue = multiprocessing.Queue()
    msg_queue = multiprocessing.Queue()

    for i in range(TASK_DURATION - 1, -1, -1):
         time_queue.put(str(datetime.timedelta(seconds=i)))

    # Add end-of-queue sentinel
    time_queue.put(None)

    start_msg = ('Your 25 minutes starts now',
                 'Working on: %s' % args.message)
    if (restart):
        notify("Time to work!", '5 minutes have passwd', sound=True)
        input('Start working now?')
    time_start = time.time()
    applet_process = launch_and_monitor(time_queue, msg_queue,
                                                      task_name=args.message,
                                                      start_msg=start_msg)
    return time_start

def finish_task():
    notify("Time's up!", 'Take a 5 minute break...', sound=True)
    if args.ondone is not None:
        os.system(args.ondone)

    input('Stop working now?')
    time_finish = time.time()
    return time_finish

def write_log(time_start, time_finish):
    if args.directory is not None:
        log_dir = args.directory
        log_file = os.path.join(args.directory, 'pomo.log')
    else:
        log_dir = APP_PATH

    if args.split:
        log_dir = os.path.join(log_dir, str(time.localtime().tm_year),
                               '{0:02d}'.format(time.localtime().tm_mon),
                               '{0:02d}'.format(time.localtime().tm_mday))

    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, 'pomo.log')

    try:
        with open(log_file, 'a') as f:
            f.writelines((str(int(time_finish - time_start)), ',',
                          args.message or '', ',',
                          str(int(time_start)), ',',
                          str(int(time_finish)), ',',
                          time.strftime('%H:%M:%S', time.localtime(time_start)), ',',
                          time.strftime('%H:%M:%S', time.localtime(time_finish)), '\n'
                      ))

    except IOError:
        print('Could not write to log file %s.' % log_file)

if __name__ == "__main__":
    if (args.startbreak):
        print('taking a break...')
        time.sleep(300)
        start = start_task(restart=True)
    else:
        start = start_task()
    finish = finish_task()
    write_log(start, finish)
    while(args.continuous):
        print('taking a break...')
        time.sleep(300)
        start = start_task(restart=True)
        finish = finish_task()
        write_log(start, finish)
