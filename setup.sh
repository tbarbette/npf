#!/bin/bash

if [ "$(whoami)" != "root" ] ; then
	echo "Please run this script with root access !"
	exit 1
fi

if [ -e /usr/bin/yum ] ; then
	i="yum -y install"
else
	i="apt-get -y install"
fi

echo "Installing python 3 and libssl"
$i python3 python3-pip libssl-dev libffi-dev

if [ -e /usr/bin/pip3 ] ; then
	p=pip3
else
	p=python3-pip
fi

function osinstall {
	echo -n "Trying to install $1 using OS package manager... "
	$i "python3-$1"
	if [ $? -ne 0 ] ; then
		echo "Failed ! Trying with pip..."
		$p "$1"
	else
		echo "OK!"
	fi
}

osinstall numpy
osinstall scipy
osinstall matplotlib
$p install -r requirements.txt
