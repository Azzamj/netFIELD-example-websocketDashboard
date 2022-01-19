from src.dashboard import dashboard
import sys
sys.path.append('../')
app = dashboard()
if __name__ == "__main__":
    app.app.run_server(debug=True,dev_tools_hot_reload=False, port='6007')