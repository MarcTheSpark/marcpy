PyCom {
	classvar pyNetAddress, allResponders;

	*initClass {
		allResponders = List.new;
	}

	*setPyNetAddress { |address|
		pyNetAddress = address;
	}

	*send { |tag, message|
		pyNetAddress.sendMsg(tag, message);
	}

	*receive { |tag, responseFunction|
		var thisResponder = OSCresponderNode(nil, tag, responseFunction).add;
		allResponders.add(thisResponder);
		^thisResponder;
	}

	*removeResponders {
		allResponders.do({ |responder|
			responder.remove;
		});
	}
}