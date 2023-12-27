# Building pebbles image

Build the docker image using pebbles dockerfile from the project root directory:

```shell script
docker build --tag pebbles:latest . --file=deployment/pebbles.Dockerfile
```

If you need to include temporary packages, say, for remote debugging, you can add those through build arguments:

```shell script
docker build --tag pebbles:latest . --file=deployment/pebbles.Dockerfile --build-arg EXTRA_PIP_PACKAGES=pydevd-pycharm
```

For deployment, see `pebbles-deploy` project.
