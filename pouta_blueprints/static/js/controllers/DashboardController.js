/* global app */
app.controller('DashboardController', ['$q', '$scope', '$interval', 'AuthService', 'Restangular', 'isUserDashboard',
                              function ($q,   $scope,   $interval,   AuthService,   Restangular,   isUserDashboard) {
        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        var blueprints = Restangular.all('blueprints');
        blueprints.getList().then(function (response) {
            $scope.blueprints = response;
        });

        var keypairs = Restangular.all('users/' + AuthService.getUserId() + '/keypairs');
        keypairs.getList().then(function (response) {
            $scope.keypairs = response;
        });

        var instances = Restangular.all('instances');

        $scope.updateInstanceList = function() {
            var queryParams = {};
            if ($scope.include_deleted) {
                queryParams.show_deleted = true;
            }
            if ($scope.limit) {
                queryParams.limit = $scope.limit;
            }
            if ($scope.offset) {
                queryParams.offset = $scope.offset;
            }
            if (AuthService.isAdmin() && isUserDashboard) {
                queryParams.show_only_mine = true;
            }
            instances.getList(queryParams).then(function (response) {
                $scope.instances = response;
            });
        };

        $scope.resetFilters = function() {
            $scope.include_deleted = false;
            $scope.limit = $scope.offset = undefined;
            $scope.updateInstanceList();
        };

        $scope.updateInstanceList();

        $scope.keypair_exists = function() {
            if ($scope.keypairs && $scope.keypairs.length > 0) {
                return true;
            }
            return false;
        };

        $scope.provision = function (blueprint) {
            instances.post({blueprint: blueprint.id}).then(function (response) {
                $scope.updateInstanceList();
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
            });
        };

        $scope.deprovision = function (instance) {
            instance.state = 'deleting';
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
                    $scope.updateInstanceList();
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
