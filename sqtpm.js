// This file is part of sqtpm 10.
// Copyright 2003-2021 Guilherme P. Telles.
// sqtpm is distributed under the terms of WTFPL v2.

function login() { 
    if (document.sqtpm.uid.value == null || document.sqtpm.uid.value == "") { 
	document.sqtpm.uid.focus(); 
    }
    else if (document.sqtpm.pwd.value == null || document.sqtpm.pwd.value == "") { 
	document.sqtpm.pwd.focus(); 
    }
    else { 
	document.sqtpm.action.value = 'in'; 
	document.sqtpm.submit(); 
    }
}


function enterh(e,name) {
    if (e.which == 13) { 
	if (name == "u") { 
	    document.sqtpm.pwd.focus(); 
	} 
	else { 
	    login();
	} 
    }
}


function wrap(action,arg1,arg2,arg3) { 
    document.sqtpm.action.value = action;
    document.sqtpm.arg1.value = arg1;
    document.sqtpm.arg2.value = arg2;
    document.sqtpm.arg3.value = arg3;
    document.sqtpm.submit(); 
}


function toggleDiv(divid){
    var e = document.getElementById(divid);
    e.style.display = (e.style.display == "none" ? "block" : "none");
}
