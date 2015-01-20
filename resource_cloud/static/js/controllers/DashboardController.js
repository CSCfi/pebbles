app.controller('DashboardController', ['$scope', '$routeParams', 'AuthService', 'Restangular',
                            function($scope, $routeParams, AuthService, Restangular) {
    
    Restangular.setDefaultHeaders({token: AuthService.getToken()});

    if (AuthService.isAdmin()) {
        var users = Restangular.all('users');
        users.getList().then(function(response) {
            $scope.users = response;
        });

        $scope.new_user = '';
        $scope.add_user = function(email) {
            var user_parameters = { email: email };
            if (email) {
                users.post(user_parameters).then(function(response) {
                    $scope.users.push(response);
                });
            }
        }

        $scope.remove_user = function(user) {
            user.remove().then(function() {
                var index = $scope.users.indexOf(user);
                if (index > -1) $scope.users.splice(index, 1);
            });
        }
    }

    var services = Restangular.all('services');
    services.getList().then(function(response) {
          $scope.services = response;
    });
    
    $scope.call_task = function() {
        services.post({})   
    }
}]);
