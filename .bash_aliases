#Place in ~/.bash_aliases
function rotary() {
        if [ "$1" = "start" ]; then
                shift
                sudo systemctl start rotary "$@"
        elif [ "$1" = "stop" ]; then
                shift
                sudo systemctl stop rotary "$@"
        elif [ "$1" = "status" ]; then
                shift
                systemctl status rotary "$@"
        else
                systemctl status rotary "$@"
        fi
}

