import flask

app = flask.Flask(__name__)
app.config["DEBUG"] = True


@app.route('/state', methods=['GET'])
def state():
    return "<h1>Distant Reading Archive</h1><p>This site is a prototype API for distant reading of science fiction novels.</p>"

@app.route('/new-recording', methods=['GET'])
def new_recording():
	return ""

app.run()