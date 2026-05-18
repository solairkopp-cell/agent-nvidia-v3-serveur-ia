from sub_services.watcher import WatcherService

if __name__ == "__main__":
    watcher = WatcherService()
    watcher.monitor_live()