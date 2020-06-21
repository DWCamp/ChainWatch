"""
SICK_FTP_Test

@author Daniel Campman
@date 2020-04-12
"""

# Standard library modules
import threading
from typing import Callable, Union

import inotify.adapters as adapters
from filewatcher.fileEvent import FileEvent


class FileWatcher:
    """
    The SICK_FTP_Test object serves as the central class for attaching
    listeners to a directory and declaring action to occur in response
    to different file events. This uses the inotify library to check for
    file changes, so it will only work on Linux.

    Once created, the `register_targets()` method can be used to declare
    callable targets that will be invoked when a specified FileEvent
    occurs. Note: there is no way to specify the order in which these
    targets are called for any given event, but the events will be
    triggered in order for any given file change.

    Once targets are registered, this watcher can be started by calling
    the `start()` method. This method is blocking and won't return until
    an outside thread calls its `stop()` method.

    It is possible to watch multiple directories, either by recursive
    watching or passing in a list of paths. In these cases, the `path`
    string passed to targets will indicate which of the watched
    directories the event occurred inside.

    :param path: The directory path(s) to watch. If a single string is
                passed in, only that directory will be watched. If a
                list of strings is passed in, each folder will be watched.
    :param recursive: Whether to watch the subdirectories as well. Defaults
                to `False` If set to 'True', then it will trigger when a
                file event occurs within a subdirectory
    :param threaded_events: Whether SICK_FTP_Test should join the threads
                for each target call or run them concurrently. Defaults to
                `True`. If set to `False` it will ensure that all targets
                finish execution before the next event is handled, however
                it will also block execution of the other events if one or
                more tasks takes a while to execute
    """

    def __init__(self, path, recursive=False, threaded_events=True):
        self._listening = False
        self._event_targets = {}
        self._threaded = threaded_events
        self._event_threads = []
        self._recursive = recursive

        self._paths = [path] if isinstance(path, str) else path  # Convert single string to list

        # Create the list for every FileEvent type
        for event in FileEvent:
            self._event_targets[event] = {}

        # Create an adapter of the right behavior
        if recursive:
            self.adapter = adapters.InotifyTrees(self._paths, block_duration_s=0.1)
        else:
            self.adapter = adapters.Inotify(block_duration_s=0.1)
            for dir_path in self._paths:
                self.adapter.add_watch(dir_path)

    def add_path(self, path) -> None:
        """
        Adds additional paths to be watched. If a path is already being watched, it
        will not be added again

        :param path: A directory (or list of directories) to add to the watchlist
        """
        paths = [path] if isinstance(path, str) else path                  # Convert single string to list
        paths = [unique for unique in paths if unique not in self._paths]  # Filter out duplicates

        if self._recursive:
            """ Unlike Inotify, InotifyTrees does not expose a method for adding directories 
            after init, so I have to make a call to one of its unexposed helper methods """
            self.adapter.__load_trees(paths)
        else:
            for new_path in paths:
                self.adapter.add_watch(new_path)

    def register_target(self, target: Callable, events: Union[FileEvent, list] = None, tag=None) -> bool:
        """
        Registers a function to be called when a file event occurs. The function must
        accept one parameter, a tuple with the following values:

            0 : FileEvent
                The inciting FileEvent type
            1 : str
                The name of the file that triggered the event
            2 : str
                The directory containing the file. If this filewatcher is not recursive,
                this will always be the target directory

        Functions are stored with tags for later removal/access. If a target with
            that tag already exists for a given FileEvent, it will not be added and
            `False` will be returned. In that case, the target will not be registered
            for any of the passed FileEvents

        Parameters
        ----------
        target : Callable
            The function to be invoked when an event occurs. If asynchronous,
            it will be added to the event loop
        events : FileEvent or list of FileEvent
            Specifies a single or group of FileEvents that the target will be
            called in response to. If no value is provided, the target will be
            registered for all events. If a list of FileEvents is given, the
            target will be registered for all types listed.
        tag : str
            The name to store this function under for later retrieval/removal.
            If none is provided, the name of the function will be used. A
            callable object with no name will be called '<Unknown>'.

        Raises
        ------
        TypeError
            If the target variable is not callable or events is not a FileEvent or list
            of FileEvents
        ValueError
            If an invalid FileEvent string was passed

        Returns
        -------
        bool
            `False` if for any events being registered for, a target with that tag
            already exists. Returns `True` otherwise
        """
        if not callable(target):
            raise TypeError("Argument 'target' was not Callable")

        if tag is None:
            tag = getattr(target, '__name__', '<Unknown>')

        # Convert events to list if 0 or 1 event was passed in
        if events is None:
            events = list(self._event_targets.keys())
        elif type(events) is not list:
            events = [events]

        # Validate arguments
        for event in events:
            # Make sure events is correct type
            if event not in self._event_targets:
                raise TypeError("Argument 'events' contains non-FileType argument: {}".format(event))
            # Make sure tag is not occupied for FileEvent
            if tag in self._event_targets[event]:
                return False

        # Add target for each type
        for event in events:
            self._event_targets[event][tag] = target

        return True

    def list_targets(self, event: FileEvent):
        """
        Returns a list of every tag registered for a given FileEvent

        :param event: The FileEvent to get the targets for
        :returns: A list of each tag registered for the provided
        """
        return list(self._event_targets[event].keys())

    def unregister_target(self, event: FileEvent, tag: str = "<Unknown>") -> bool:
        """
        Returns every tag registered for a given FileEvent.

        :param event: The FileEvent to remove the target from
        :param tag: The tag the target was stored under. If no tag was
                    provided at registration, this will be the function's
                    name. If no tag is provided, it will default to
                    '<Unknown>', the tag for non-function callables
                    (e.g. lambdas)
        :returns: Returns `False` if no target was stored under that tag,
                    or if the FileEvent provided does not exist. Returns
                    `True` otherwise
        """
        if event not in self._event_targets or tag not in self._event_targets[event]:
            return False
        del self._event_targets[event][tag]
        return True

    def listen(self):
        """
        Prints all file events an adapter has seen. Additionally,
        all targets for that event will be called with the name
        of the file the event was triggered on and the path to its
        containing folder (relative to the watched directory)

        Note: For events where the triggering item is a directory,
        the filename will be an empty string
        """
        for item in self.adapter.event_gen():
            # Break out of generator if SICK_FTP_Test stopped
            if not self._listening:
                break

            # Ignore None events. They can't be ignored or the generator
            # will indefinitely block in between file events
            if item is None:
                continue

            (_, type_names, path, filename) = item
            for event_name in type_names:
                event = FileEvent(event_name)
                self._event_threads = []
                for tag, target in self._event_targets[event].items():
                    data = (event, filename, path)
                    thread = threading.Thread(target=target, args=(data,))
                    thread.start()
                    self._event_threads.append(thread)
                # If event threading is turned off, wait until all
                # threads have finished to continue
                if not self._threaded:
                    for spawned_thr in self._event_threads:
                        spawned_thr.join()

    def start(self):
        """
        Starts the SICK_FTP_Test listening to the directory

        Note: This function is blocking, so it can only be
        stopped by an asynchronous function or another thread
        """
        if not self._listening:
            self._listening = True
            self.listen()

    def is_listening(self):
        """
        Returns whether this SICK_FTP_Test is currently listening for file events

        :return: `True` if this object is listening, `False` otherwise
        """
        return self._listening

    def stop(self):
        """
        Turns off the SICK_FTP_Test. This will unblock the call to `start()`,
        but if SICK_FTP_Test is has threaded_events disabled, it will unblock
        only once all targets have completed. Calling `start()` again will
        resume file listening.
        """
        print("Stopping...")
        self._listening = False
