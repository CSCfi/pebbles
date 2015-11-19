app.controller('StatsController', ['$q', '$scope', '$http', '$interval', '$uibModal', 'AuthService', 'Restangular',
                              function ($q,   $scope,   $http,   $interval,   $uibModal,   AuthService,   Restangular) {

        Restangular.setDefaultHeaders({token: AuthService.getToken()});
        var stats = Restangular.all('stats');

        stats.getList().then(function (response) {
            $scope.stats = response[0];
        });
    }]);
