app.controller('NavbarController', ['$scope', '$window', '$rootScope', '$location', '$routeParams', 'AuthService', 'ConfigurationService', function($scope, $window, $rootScope, $location, $routeParams, AuthService, ConfigurationService) {
    var _invalidLogin = false;
    var _showLoginBox = undefined;
 
    $scope.setLoginStatus = function (data){
        /* login box should not be visible by default if oauth2 is enabled.
         * but obviously should be if it is not. */
        _showLoginBox = ! data['OAUTH2_LOGIN_ENABLED'];
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
        AuthService.login($scope.eppn, $scope.password).then(function() {
            _invalidLogin = false;
            $rootScope.$broadcast('userLoggedIn');
            _routeNavigator();
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

    $scope.getIcons = function() {
        if (AuthService.getIcons()) {
            return AuthService.getIcons();
        }
        else {
            return false;
        }
    };

    $scope.isWorkspaceOwnerOrAdmin = function() {
        return AuthService.isWorkspaceOwnerOrAdmin();
    };

    $scope.isWorkspaceManagerOrAdmin = function() {
        return AuthService.isWorkspaceManagerOrAdmin();
    };

    $scope.logout = function() {
        AuthService.logout();
        $scope.eppn = "";
        $scope.password = "";
        $rootScope.$broadcast('userLoggedOut');
        // To make transition smoother
        $location.path(' ');
        hostname = $window.location.hostname;
        urlvalue = '/oauth2/sign_out';
        $window.location.href = urlvalue;
    };

    var _routeNavigator = function() {
        if($routeParams.environment_id){
            $location.url($location.path());  // remove query parameters when navigating further
            $location.path("/environment/" + $routeParams.environment_id);
        }
        else{
            $location.path("/dashboard");
        }
    };

}]);
