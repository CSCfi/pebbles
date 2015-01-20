app.controller('AuthController', ['$scope', '$location', 'AuthService', function($scope, $location, AuthService) {
    $scope.isLoggedIn = function() {
        return AuthService.isAuthenticated();
    };

    $scope.login = function() {
        AuthService.login($scope.email, $scope.password).then(function() {
        })
    };

    $scope.logout = function() {
        AuthService.logout();
        $scope.email = "";
        $scope.password = "";
        $location.path("/");
    };
}]);
