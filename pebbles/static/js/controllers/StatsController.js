app.controller('StatsController', ['$q', '$scope', '$http', '$interval', '$uibModal', 'AuthService', 'Restangular',
                              function ($q,   $scope,   $http,   $interval,   $uibModal,   AuthService,   Restangular) {

        $scope.getIcons = function() {
            return AuthService.getIcons()[5];
        };

        Restangular.setDefaultHeaders({token: AuthService.getToken()});
        var stats = Restangular.oneUrl('stats');

        stats.get().then(function (response) {
            $scope.stats = response;
        });
    }]);
