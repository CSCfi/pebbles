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

        $scope.provision = function (resource) {
            provisionedResources.post({resource: resource.id}).then(function (response) {
                    provisionedResources.getList().then(function (response) {
                            $scope.instances = response;
                        }
                    );
                }
            );
        };

        $scope.deprovision = function (provisionedResource) {
            provisionedResource.patch({state: 'deleting'}).then(function () {
                var index = $scope.instances.indexOf(provisionedResource);
                if (index > -1) {
                    $scope.instances[index].state = 'deleting';
                }
            });
        };

        var stop;
        $scope.startPolling = function() {
            if (angular.isDefined(stop)) {
                return;
            }
            stop = $interval(function () {
                if (AuthService.isAuthenticated()) {
                    var provisionedResources = Restangular.all('provisioned_resources');
                    provisionedResources.getList().then(function (response) {
                        $scope.instances = response;
                    });
                } else {
                    $interval.cancel(stop);
                }
            }, 10000);
        };

        $scope.stopPolling = function() {
            if (angular.isDefined(stop)) {
                $interval.cancel(stop);
                stop = undefined;
            }
        }

        $scope.$on('$destroy', function() {
            $scope.stopPolling();
        });

        $scope.startPolling();
    }]);
