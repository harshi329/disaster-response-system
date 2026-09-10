from dotenv import load_dotenv
load_dotenv(override=True)

from app import create_app
import os

app = create_app()

if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
