function handle(name)
{
	action = document.getElementById("output-" + name);
	img = document.getElementById("img-" + name);
	old_src = img.getAttribute("src");

	current_display = action.style.display;

	// try to handle the case where the display is not explicitly set
	if (current_display == "") {
		if (action.currentStyle) { // ack, IE
			current_display = action.currentStyle.display;
		}
		else if (document.defaultView.getComputedStyle) { // oooh, DOM
			var style_list = document.defaultView.getComputedStyle(action, "");

			// konqueor has getComputedStyle, but it does not work
			if (style_list != null) {
				current_display = style_list.getPropertyValue("display");
			}
		}
		// in the case than neither works, we will do nothing. it just
		// means the user will have to click twice to do the initial
		// closing
	}

	if (current_display == "block") {
		action.style.display = "none";
		img.setAttribute("src", old_src.replace("hide", "unhide"));
	}
	else {
		action.style.display = "block";
		img.setAttribute("src", old_src.replace("unhide", "hide"));
	}
}
