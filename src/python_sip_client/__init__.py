import time
import logging
import threading
import pexpect
import enum
import types

class BareSIP:

    # Types
    class Event(enum.Enum):
        READY = "READY",
        CALLING = "CALLING",
        ANSWERED = "ANSWERED",
        INCOMING_CALL = "INCOMING_CALL",
        TERMINATED = "TERMINATED",
        UA_REGISTED = "UA_REGISTED",

    class UserAgent:
        def __init__(self, user: str, domain: str, registered: bool, uri: str):
            self.user = user
            self.domain = domain
            self.registered = registered
            self.uri = uri
            self._current_call = None

        def __str__(self):
            return f"User: {self.user}, Domain: {self.domain}, Registered: {self.registered}, URI: {self.uri}"
    
        def __repr__(self):
            return self.__str__()

    # TODO - Implement configuration
    # from baresip_configuration import BareSIPConfiguration

    # Con/descructors
    def __init__(self, debug=False):
        ## Configuration
        self._debug = debug
        self._timeout = 10 # 10 Second default timeout for essential tasks
        self._timeout_check_frequency = 1000 # Hz
        self._logger = None

        ## Process, Thread, States
        self._process = None
        self._thread = None
        self._stop_event = threading.Event()
        self._is_running = False
        self._is_ready = False

        # Objects
        self._user_agents = []

        ## Response queues (semaphores)
        self._semaphore_user_agents = 0

        # Public
        @property
        def is_running(self):
            return self._is_running
        
        def is_ready(self):
            return self._is_ready

        ## Callbacks
        self._callbacks = {
            self.Event.READY: None,
            self.Event.INCOMING_CALL: None,
            self.Event.CALLING: None,
            self.Event.ANSWERED: None,
            self.Event.TERMINATED: None,
            self.Event.UA_REGISTED: None,
        }

        ## Logger Setup
        logging.basicConfig(level=logging.DEBUG if debug else logging.WARNING)

        self._logger = logging.getLogger(self.__class__.__name__)
        self._logger.propagate = 0
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG if debug else logging.WARNING)
        ch.setFormatter(self._BareSIPLogFormatter())
        self._logger.addHandler(ch)

    def __del__(self):
        if self._process:
            self.stop()

    class _BareSIPLogFormatter(logging.Formatter):

        cyan = "\x1b[36m"
        grey = "\x1b[38;20m"
        yellow = "\x1b[33;20m"
        red = "\x1b[31;20m"
        bold_red = "\x1b[31;1m"
        reset = "\x1b[0m"
        format = "%(levelname)s : %(name)s : %(message)s"

        FORMATS = {
            logging.DEBUG: cyan + format + reset,
            logging.INFO: grey + format + reset,
            logging.WARNING: yellow + format + reset,
            logging.ERROR: red + format + reset,
            logging.CRITICAL: bold_red + format + reset
        }

        def format(self, record):
            log_fmt = self.FORMATS.get(record.levelno)
            formatter = logging.Formatter(log_fmt)
            return formatter.format(record)

    # Private methods
    def _send(self, command: str) -> bool:
        if self._is_ready:
            self._process.sendline(command)
            return True
        else:
            self._logger.error("attempt to write while process is not running")
            return False
 
    def _parse(self):
        self._logger.debug("output parser active")

        while not self._stop_event.is_set():
            self._process_line()

        self._logger.debug("output parser stopped")

    def _process_line(self):
        try:
            # TODO - compile list pattern
            expectations = [
                "baresip is ready.",
                "--- User Agents ",
                "useragent registered successfully",
                "Incoming call from: ",
                "Call in-progress: ",
                "could not find UA",
                "Call answered: ",
                "session closed",
            ]

            # print(self._process.readline().strip())

            expectation = expectations[self._process.expect(expectations, timeout=0)]
        
            if expectation == "baresip is ready.":
                self._is_ready = True

                self._logger.debug("baresip is ready")

                if isinstance(self._callbacks[self.Event.READY], types.FunctionType):
                    self._callbacks[self.Event.READY]()

                return
            
            if expectation == "--- User Agents ":
                # Process output format: "--- User Agents (#)"
                # ......................."0: <sip:user@domain> - OK"
                # ......................."1: <sip:user@domain> - zzz"
                line = self._process.readline().strip()
                agents_count = int(line[line.index("(") + 1:line.index(")")])

                # Clear user agents
                self._user_agents = [] 

                # For each discovered user agent
                for i in range(agents_count):
                    self._process.expect([str(i), ">"])
                    # Process each line
                    line = (self._process.readline().strip())[2:]
                    print(f"line: {line}")
                    uri = line[:line.index(" ")]
                    user = uri[uri.index(":") + 1:uri.index("@")]
                    domain = uri[uri.index("@") + 1:]
                    registered = "OK" in line

                    # Create user agent object
                    self._user_agents.append(self.UserAgent(user, domain, registered, uri))

                # Release semaphore
                self._semaphore_user_agents = 0

                self._logger.debug(f"Found {len(self._user_agents)} User Agents")

                return

            if expectation == "useragent registered successfully":
                if isinstance(self._callbacks[self.Event.UA_REGISTED], types.FunctionType):
                    self._callbacks[self.Event.UA_REGISTED]()

                return
            
            # User dialed a number, went through
            if expectation == "Call in-progress: ":
                uri = self._process.readline().strip()

                self._logger.debug(f"call in-progress: {uri}")
                
                if isinstance(self._callbacks[self.Event.CALLING], types.FunctionType):
                    self._callbacks[self.Event.CALLING](uri)

                return
            
            # Other client answered
            if expectation == "Call answered: ":
                uri = self._process.readline().strip()

                self._logger.debug(f"call answered: {uri}")
                
                if isinstance(self._callbacks[self.Event.ANSWERED], types.FunctionType):
                    self._callbacks[self.Event.ANSWERED](uri)

                return

            # Other client hung up
            if expectation == "session closed":
                self._process.readline()
                line = self._process.readline().strip()

                uri = ''.join(line.split("Call with ")[1].split(" terminated")[0])

                self._logger.debug(f"call terminated: {uri}")

                if isinstance(self._callbacks[self.Event.TERMINATED], types.FunctionType):
                    self._callbacks[self.Event.TERMINATED](uri)

            # No user agent
            if expectation == "could not find UA":
                self._logger.error("attempted to dial without registered user agent")
                return

            # Incoming call
            if expectation == "Incoming call from: ":
                line = self._process.readline().strip()
                uri = line[line.index(" ") + 1:line.index(" - ")]
                
                self._logger.debug(f"incoming call from: {uri}")

                if isinstance(self._callbacks[self.Event.INCOMING_CALL], types.FunctionType):
                    self._callbacks[self.Event.INCOMING_CALL](uri)

                return
            
        except pexpect.EOF:
            self._logger.error("parser recieved EOF")
            self.stop()
        except pexpect.TIMEOUT:
            pass
        except Exception as e:
            self._logger.error("error reading line", e)
        return

    def _wait_for_ready(self):
        for _ in range(self._timeout * self._timeout_check_frequency):
            if self._is_ready:
                return
            time.sleep(1 / self._timeout_check_frequency)

    # Public methods
    def start(self): #TODO - Arguments for config
        # Create process
        self._process = pexpect.spawn('baresip', encoding='utf-8')
        # Do parsing on separate thread
        self._thread = threading.Thread(target=self._parse, daemon=True)
        self._thread.start()

        self._is_running = True
        self._wait_for_ready()

    def stop(self):
        # Stop Parser
        if not self._stop_event.is_set():
            self._stop_event.set()

        # Delete parser thread
        if self._thread is not None:
            self._thread.join()
            self._logger.debug("parser thread stopped")
            self._thread = None
            self._process = None

        # Stop process
        if self._process:
            self._send("/quit")
            self._process.wait()
            self._process.terminate()
            self._logger.debug("baresip stopped")

        self._is_running = False

    # Sets callbacks for events
    def on(self, event: Event, callback: types.FunctionType) -> bool:
        # Check that callback for the given event is a function
        if not isinstance(callback, types.FunctionType):
            self._logger.error(f"callback must be a function, not {type(callback)}")
            return False
        
        # Check that event is valid
        if not event in self.Event:
            self._logger.error(f"invalid event {event}")
            return False
        
        # Set callback
        self._callbacks[event] = callback

        return True

    # /reginfo
    def user_agents(self):
        # Wait for response using semaphore
        # Increase semaphore value before sending command, since it will
        # immediately produce output
        self._semaphore_user_agents = 1

        # Send command
        self._send("/reginfo")

        # Wait for resources to be released before continuing
        for _ in range(self._timeout_check_frequency * self._timeout):
            if not self._semaphore_user_agents == 1:
                return self._user_agents
            
            time.sleep(1 / self._timeout_check_frequency)
        
        self._logger.error("timeout waiting for user agents")

        return None

    # /uanew
    def create_user_agent(self, user: str, password: str, domain: str):
        # Wait for response using semaphore
        # Increase semaphore value before sending command, since it will
        # immediately produce output
        self._semaphore_user_agents = 2

        # Send command
        self._send(f"/uanew <sip:{user}@{domain}>;auth_pass=\"{password}\"")

        # Wait for resources to be released before continuing
        for _ in range(self._timeout_check_frequency * self._timeout):
            if not self._semaphore_user_agents == 2:
                return self._user_agents[-1] if len(self._user_agents) > 0 else None
            
            time.sleep(1 / self._timeout_check_frequency)
        
        self._logger.error("timeout waiting for user agents")

        return None

    # /dial
    def dial(self, address: str):
        self._send(f"/dial {address}")

    # /hangup
    def hangup(self):
        self._send("/hangup")

    # /hangupall
    def hangup_all(self):
        self._send("/hangupall")

    # /answer
    def answer(self):
        self._send("/answer")
