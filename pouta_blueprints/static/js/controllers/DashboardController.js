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
                }, function(response) {

                    if (response.status != 409) {
                        $.notify({title: 'HTTP ' + response.status, message: 'unknown error'}, {type: 'danger'});
                    } else {
                        if (response.data.error == 'USER_OVER_QUOTA') {
                            $.notify({title: 'HTTP ' + response.status, message: 'User quota exceeded, contact your administrator in order to get more'}, {type: 'danger'});
                        } else {
                            $.notify({title: 'HTTP ' + response.status, message: 'Maximum number of running instances for the selected blueprint reached.'}, {type: 'danger'});
                        }
                    }
                }
            );
        };

        $scope.deprovision = function (instance) {
            instance.state = 'deprovisioning';
            instance.error_msg = '';
            instance.remove();
        };

        $scope.isAdmin = function() {
            return AuthService.isAdmin();
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
