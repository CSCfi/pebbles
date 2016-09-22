app.controller('NavbarController', ['$scope', '$rootScope', '$location', 'AuthService', 'ConfigurationService', function($scope, $rootScope, $location, AuthService, ConfigurationService) {
    var _invalidLogin = false;
    var _showLoginBox = undefined;

    $scope.setLoginStatus = function (data){
        /* login box should not be visible by default if shibboleth is enabled.
         * but obviously should be if it is not. */
        _showLoginBox = ! data['ENABLE_SHIBBOLETH_LOGIN'];
    };

    ConfigurationService.getValue().then($scope.setLoginStatus);

    $scope.toggleLoginVisibility = function(){
        _showLoginBox = ! _showLoginBox;
    };

    $scope.getLoginVisibility = function(){
        return _showLoginBox;
    };

    $scope.isLoggedIn = function() {
        return AuthService.isAuthenticated();
    };

    $scope.isLoggedOut = function() {
        return ! AuthService.isAuthenticated();
    };

    $scope.loginFormHidden = function(viewLocation) {
        return $location.path().match(viewLocation) === viewLocation;
    };
    $scope.login = function() {
        AuthService.login($scope.email, $scope.password).then(function() {
            _invalidLogin = false;
            $rootScope.$broadcast('userLoggedIn');
            $location.path("/dashboard");
        }, function() {
            _invalidLogin = true;
        });
    };

    $scope.isActive = function (viewLocation) {
        return viewLocation === $location.path();
    };

    $scope.invalidLogin = function() {
        return _invalidLogin;
    };

    $scope.getUserName = function() {
        if ($scope.isLoggedIn()) {
            return AuthService.getUserName();
        }
    };

    $scope.isAdmin = function() {
        return AuthService.isAdmin();
    };

    $scope.isGroupOwnerOrAdmin = function() {
        return AuthService.isGroupOwnerOrAdmin();
    };

    $scope.logout = function() {
        AuthService.logout();
        $scope.email = "";
        $scope.password = "";
        $rootScope.$broadcast('userLoggedOut');
        $location.path("/");
    };
}]);
