app.controller('DashboardController', ['$q', '$scope', '$interval', 'AuthService', 'Restangular',
                              function ($q,   $scope,   $interval,   AuthService,   Restangular) {

        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        var resources = Restangular.all('resources');
        resources.getList().then(function (response) {
            $scope.services = response;
        });

        var provisionedResources = Restangular.all('provisioned_resources');
        provisionedResources.getList().then(function (response) {
            $scope.instances = response;
        });

        $scope.showAdminOptions = function() {
            return AuthService.isAdmin();
        }

        var currentService = null;
        $scope.selectService = function(service) {
            currentService = service;
            $scope.config = currentService.config;
        }

        $scope.updateConfig = function() {
            currentService.config = $scope.config;
            currentService.put();
        }
        $scope.provision = function (resource) {
            resource.post().then(function (response) {
                    provisionedResources.getList().then(function (response) {
                            $scope.instances = response;
                        }
                    )
                }
            )
            ;
        }

        $scope.deprovision = function (provisionedResource) {
            provisionedResource.patch({state:'deleting'}).then(function () {
                var index = $scope.instances.indexOf(provisionedResource);
                if (index > -1) $scope.instances[index].state='deleting';
            });
        }

        var pollInterval = $interval(function () {
            if (AuthService.isAuthenticated()) {
                var provisionedResources = Restangular.all('provisioned_resources');
                provisionedResources.getList().then(function (response) {
                    $scope.instances = response;
                });
            } else {
                $interval.cancel(pollInterval);
            }
        }, 10000);
    }]);
