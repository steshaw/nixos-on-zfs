from pybootstrap import configure, install, partition, prepare

def c(msg):
    input(f"About to {msg} [press enter to continue]")

def main():
    c("config")
    config = prepare.prepare()
    c("parition")
    partition.partition(config=config)
    c("configure")
    configure.configure(config=config)
    c("install")
    install.install(config=config)

if __name__ == "__main__":
    main()
