app.controller('ConfigureController', ['$q', '$scope', '$http', '$interval', 'AuthService', 'Restangular',
                              function ($q,   $scope,   $http,   $interval,   AuthService,   Restangular) {

        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        var plugins = Restangular.all('plugins');

        plugins.getList().then(function (response) {
            $scope.plugins = response;
        });

        var resources = Restangular.all('resources');

        resources.getList({show_deactivated: true}).then(function (response) {
            $scope.resources = response;
        });

        $scope.submitForm = function(form, model) {
            if (form.$valid) {
                resources.post({ plugin: $scope.selectedPlugin.id, name: model.name, config: model }).then(function (response) {
                        resources.getList({show_deactivated: true}).then(function (response) {
                                $scope.resources = response;
                            }
                        )
                    }
                );
                $('#resourceCreate').modal('hide')
            }
        }
        $scope.create = function () {
            if (form.$valid) {
                resources.post({ plugin: $scope.plugin, name: $scope.name, config: $scope.config }).then(function (response) {
                        resources.getList({show_deactivated: true}).then(function (response) {
                                $scope.resources = response;
                            }
                        )
                    }
                );
                $('#resourceCreate').modal('hide')
            }
        }

        $scope.selectPlugin = function(plugin) {
            $scope.selectedPlugin = plugin;
            $scope.$broadcast('schemaFormRedraw')
        }

        $scope.selectResource = function(resource) {
            $scope.currentResource = resource;
        }

        $scope.createResource = function() {
            var newResource = {};
            newResource.name = $scope.name;
            newResource.config = $scope.config;
            newResource.plugin = $scope.plugin;
            resources.post(newResource);
        }

        $scope.updateConfig = function() {
            $scope.currentResource.put();
            $('#resourceConfig').modal('hide')

        }

        

        $scope.activate = function (resource) {
            resource.is_enabled = true;
            resource.put();
        }

        $scope.deactivate = function (resource) {
            resource.is_enabled = undefined;
            resource.put();
        }

    }]);
