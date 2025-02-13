# Add to ~/.bash_aliases
function rotary() {
	if [ "$1" = "start" ]; then
		shift
		sudo systemctl start rotary "$@"
	elif [ "$1" = "stop" ]; then
		shift
		sudo systemctl stop rotary "$@"
	elif [ "$1" = "restart" ]; then
		shift
		sudo systemctl restart rotary "$@"
	elif [ "$1" = "status" ]; then
		shift
		systemctl status rotary "$@"
	elif [ "$1" = "test" ]; then
		shift
		python ~/Documents/rotary/rotary/src/main.py "$@"
	else
		systemctl status rotary "$@"
	fi
}

