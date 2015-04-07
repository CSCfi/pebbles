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

        var keypairs = Restangular.all('users/' + AuthService.getUserId() + '/keypairs');
        keypairs.getList().then(function (response) {
            $scope.keypairs = response;
        });

        $scope.keypair_exists = function() {
            if ($scope.keypairs && $scope.keypairs.length > 0) {
                return true;
            }
            return false;
        };

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
            instance.state = 'deleting';
            instance.error_msg = '';
            instance.remove();
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
