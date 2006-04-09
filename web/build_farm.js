function handle(name)
{
	// get a reference to the output block
	outputBlock = document.getElementById("output-" + name);

	// and the image that's next to the block
	img = document.getElementById("img-" + name);

	old_src = img.getAttribute("src");

	current_display = outputBlock.style.display;

	// try to handle the case where the display is not explicitly set
	if (current_display == "") {
		if (outputBlock.currentStyle) { // ack, IE
			current_display = outputBlock.currentStyle.display;
		}
		else if (document.defaultView.getComputedStyle) { // oooh, DOM
			var style_list = document.defaultView.getComputedStyle(outputBlock, "");

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
		outputBlock.style.display = "none";
		img.setAttribute("src", old_src.replace("hide", "unhide"));
	}
	else {
		outputBlock.style.display = "block";
		img.setAttribute("src", old_src.replace("unhide", "hide"));
	}
}
