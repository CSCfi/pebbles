/* global app */
app.controller('DashboardController', ['$q', '$scope', '$interval', 'AuthService', 'Restangular',
                              function ($q,   $scope,   $interval,   AuthService,   Restangular) {

        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        var blueprints = Restangular.all('blueprints');
        blueprints.getList().then(function (response) {
            $scope.blueprints = response;
        });

        var instances = Restangular.all('instances');
        instances.getList().then(function (response) {
            $scope.instances = response;
        });

        $scope.provision = function (blueprint) {
            instances.post({blueprint: blueprint.id}).then(function (response) {
                    instances.getList().then(function (response) {
                            $scope.instances = response;
                        }
                    );
                }
            );
        };

        $scope.deprovision = function (instance) {
            instance.patch({state: 'deleting'}).then(function () {
                var index = $scope.instances.indexOf(instance);
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
                    var instances = Restangular.all('instances');
                    instances.getList().then(function (response) {
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
        };

        $scope.$on('$destroy', function() {
            $scope.stopPolling();
        });

        $scope.startPolling();
    }]);
