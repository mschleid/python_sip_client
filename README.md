# python_sip_client - A baresip-based, multithreaded, event handling SIP client written in Python

### Requirements

This package acts as a wrapper for [BareSIP](https://github.com/baresip/baresip), which is required for this package to function. For installation instructions, see the [BareSIP Repository](https://github.com/baresip/baresip). Typically, it can be installed using your favorite linux/macos package manager.

## Example Usage
    from python_sip_client import BareSIP
    import time

    if __name__ == "__main__":
        # Create BareSIP instance
        bs = BareSIP(debug=False)

        # Define event handlers
        def handle_incoming_call(from_uri):
            print("Incoming call from", from_uri)
            
            x = None
            while x.lower() not in ["a", "h"]:
                x = input("Answer or hangup? (a/h): ")
            
            if x == "a":
                bs.answer()
            else:
                bs.hangup()

        # Set event handlers
        bs.on(BareSIP.Event.INCOMING_CALL, handle_incoming_call)

        try:
            # Start BareSIP
            bs.start()
            
            # Create a user agent
            bs.create_user_agent("user", "password", "domain")

            # Wait for registration
            while not bs.user_agents()[0].registered:
                pass

            bs.dial("user@domain / phone number")

            time.sleep(10)

            bs.hangup()

            while True:
                pass
        finally:
            # Stop BareSIP
            bs.stop()